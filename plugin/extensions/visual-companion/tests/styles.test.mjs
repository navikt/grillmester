import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { createServerBackend } from '../backend.mjs';

async function fixture(run) {
  const directory = await mkdtemp(join(tmpdir(), 'canvas-styles-'));
  const projectDir = await realpath(directory), backends = [];
  const open = async options => {
    const backend = await createServerBackend({ projectDir, ...options });
    backends.push(backend);
    return backend;
  };
  try { await run({ projectDir, open }); }
  finally {
    await Promise.all(backends.map(backend => backend.retire()));
    await rm(directory, { recursive: true, force: true });
  }
}

async function installStyles(projectDir, subproject, version, marker) {
  const packageDir = join(projectDir, subproject, 'node_modules/@navikt/ds-css');
  await mkdir(join(packageDir, 'dist'), { recursive: true });
  await writeFile(join(packageDir, 'package.json'), JSON.stringify({ name: '@navikt/ds-css', version }));
  const css = `.navds-heading { --style-proof: ${marker}; }\n`;
  await writeFile(join(packageDir, 'dist/index.min.css'), css);
  return { packageDir, css, sha256: createHash('sha256').update(css).digest('hex') };
}

async function preview(backend) {
  const view = await backend.openView({});
  const state = await backend.readState({});
  if (!state.screen) await backend.publishRevision({ expectedScreen: '', filename: 'first.html', html: '<h1 class="navds-heading">Skisse</h1>' });
  const url = new URL(view.url); url.pathname = '/preview';
  return (await fetch(url, { signal: AbortSignal.timeout(3000) })).text();
}

test('selected subproject CSS is rendered and receipted without changing root room storage', () => fixture(async ({ projectDir, open }) => {
  const root = await installStyles(projectDir, '', '8.8.0', 'root-only');
  const app = await installStyles(projectDir, 'apps/frontend', '8.9.0', 'app-only');
  const backend = await open({ workspacePath: 'designs/room', create: true, styleProjectPath: 'apps/frontend' });
  const state = await backend.readState({});
  assert.deepEqual(state.styles, { styleProjectPath: 'apps/frontend', status: 'loaded',
    source: 'apps/frontend/node_modules/@navikt/ds-css/dist/index.min.css', version: '8.9.0', sha256: app.sha256 });
  assert.equal(state.workspace.path, 'designs/room');
  const html = await preview(backend);
  assert(html.includes(app.css)); assert(!html.includes(root.css));
  assert.doesNotMatch(html, /Aksel CSS mangler/);
  assert.equal(JSON.parse(await readFile(join(projectDir, 'designs/room/workspace.json'), 'utf8')).workspace.version, 1);
  await assert.rejects(readdir(join(projectDir, 'apps/frontend/designs')), error => error.code === 'ENOENT');
  await backend.closeView({}); await backend.openView({});
  assert.deepEqual((await backend.readState({})).styles, state.styles);
}));

test('root defaults and explicit empty selectors stay compatible; new owners must select styling again', () => fixture(async ({ projectDir, open }) => {
  const root = await installStyles(projectDir, '', '8.8.0', 'root-only');
  await installStyles(projectDir, 'apps/frontend', '8.9.0', 'app-only');
  const first = await open({ workspacePath: 'designs/room', create: true, styleProjectPath: 'apps/frontend' });
  const initial = await first.readState({}); await first.retire();
  const next = await open({ workspacePath: 'designs/room' });
  const recovered = await next.readState({});
  assert.equal(recovered.workspace.id, initial.workspace.id);
  assert.equal(recovered.styles.styleProjectPath, ''); assert.equal(recovered.styles.version, '8.8.0');
  assert.equal(recovered.styles.sha256, root.sha256);
  const explicit = await open({ styleProjectPath: '' });
  assert.deepEqual((await explicit.readState({})).styles, recovered.styles);
  assert.equal(JSON.parse(await readFile(join(projectDir, 'designs/room/workspace.json'), 'utf8')).styles, undefined);
}));

test('internal pnpm links load the selected installed version when root CSS is absent', () => fixture(async ({ projectDir, open }) => {
  const installed = await installStyles(projectDir, 'node_modules/.pnpm/styles-at-8.9.0', '8.9.0', 'pnpm-app-only');
  const link = join(projectDir, 'apps/frontend/node_modules/@navikt/ds-css');
  await mkdir(dirname(link), { recursive: true }); await symlink(installed.packageDir, link);
  const backend = await open({ styleProjectPath: 'apps/frontend' });
  const state = await backend.readState({});
  assert.equal(state.styles.status, 'loaded'); assert.equal(state.styles.version, '8.9.0');
  assert.equal(state.styles.sha256, installed.sha256);
  assert.equal(state.styles.source, 'apps/frontend/node_modules/@navikt/ds-css/dist/index.min.css');
  assert((await preview(backend)).includes(installed.css));
}));

test('missing exact selection never uses root or another app and exposes a fallback receipt', () => fixture(async ({ projectDir, open }) => {
  const root = await installStyles(projectDir, '', '8.8.0', 'root-only');
  const other = await installStyles(projectDir, 'apps/other', '8.9.0', 'other-only');
  const backend = await open({ styleProjectPath: 'apps/missing' });
  assert.deepEqual((await backend.readState({})).styles, { styleProjectPath: 'apps/missing', status: 'fallback',
    source: null, version: null, sha256: null, reason: 'missing' });
  const html = await preview(backend);
  assert.match(html, /Aksel CSS mangler/); assert(!html.includes(root.css)); assert(!html.includes(other.css));
}));

test('escaping subproject parents and dependency links cannot load external CSS', () => fixture(async ({ projectDir, open }) => {
  const outside = await mkdtemp(join(tmpdir(), 'canvas-outside-styles-'));
  try {
    const external = await installStyles(outside, '', '9.9.9', 'external-must-stay-private');
    await mkdir(join(projectDir, 'apps'), { recursive: true });
    await symlink(outside, join(projectDir, 'apps/escape'));
    const dependencyLink = join(projectDir, 'apps/linked/node_modules/@navikt/ds-css');
    await mkdir(dirname(dependencyLink), { recursive: true }); await symlink(external.packageDir, dependencyLink);
    for (const styleProjectPath of ['apps/escape', 'apps/linked']) {
      const backend = await open({ styleProjectPath });
      const styles = (await backend.readState({})).styles;
      assert.equal(styles.status, 'fallback'); assert.equal(styles.reason, 'rejected');
      assert.equal(styles.source, null); assert.equal(styles.version, null); assert.equal(styles.sha256, null);
      assert(!(await preview(backend)).includes(external.css));
    }
  } finally { await rm(outside, { recursive: true, force: true }); }
}));

test('symlinked CSS leaves remain rejected even when their target is inside the project', () => fixture(async ({ projectDir, open }) => {
  const root = await installStyles(projectDir, '', '8.8.0', 'must-not-follow-leaf');
  const selected = join(projectDir, 'apps/frontend/node_modules/@navikt/ds-css/dist/index.min.css');
  await mkdir(dirname(selected), { recursive: true }); await symlink(join(root.packageDir, 'dist/index.min.css'), selected);
  const backend = await open({ styleProjectPath: 'apps/frontend' });
  assert.equal((await backend.readState({})).styles.reason, 'rejected');
  assert(!(await preview(backend)).includes(root.css));
}));

test('missing or invalid package version does not invent provenance for loaded CSS', () => fixture(async ({ projectDir, open }) => {
  const installed = await installStyles(projectDir, 'apps/frontend', 'not-a-version', 'unversioned-css');
  const backend = await open({ styleProjectPath: 'apps/frontend' });
  const styles = (await backend.readState({})).styles;
  assert.equal(styles.status, 'loaded'); assert.equal(styles.version, null); assert.equal(styles.sha256, installed.sha256);
  assert((await preview(backend)).includes(installed.css));
}));
