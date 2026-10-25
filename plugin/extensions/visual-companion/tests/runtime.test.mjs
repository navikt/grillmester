import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, mkdtemp, mkdir, readFile, readdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, delimiter, join } from 'node:path';
import { previewEnvironment, resolveNodeRuntime } from '../runtime.mjs';

async function fixture(run) {
  const root = await mkdtemp(join(tmpdir(), 'preview-runtime-'));
  const projectDir = join(root, 'project');
  await mkdir(projectDir);
  try { await run({ root, projectDir }); }
  finally { await rm(root, { recursive: true, force: true }); }
}

async function executable(filename, source) {
  // An explicit mode keeps runtime folders protected under a permissive umask.
  await mkdir(dirname(filename), { recursive: true, mode: 0o755 });
  await writeFile(filename, `#!${process.execPath}\n${source}\n`, { mode: 0o700 });
}

// Records each execution, then reports the Node that runs the script.
const recordingRuntime = marker => `
  require('node:fs').appendFileSync(${JSON.stringify(marker)}, 'x');
  process.stdout.write(JSON.stringify({ protocol: 'preview-node-runtime-v1', version: process.versions.node,
    executable: process.execPath, ordinary: true }));
`;

test('an ordinary current Node is preferred even without PATH', () => fixture(async ({ projectDir }) => {
  assert.equal(await resolveNodeRuntime({ projectDir, path: '' }), await realpath(process.execPath));
}));

test('a bundled host is never reentered and PATH supplies an ordinary Node', () => fixture(async ({ root, projectDir }) => {
  const entered = join(root, 'host-entered'), host = join(root, 'bundled-host');
  await executable(host, `require('node:fs').writeFileSync(${JSON.stringify(entered)}, 'entered'); process.exit(1);`);
  const bin = join(root, 'bin'); await mkdir(bin); await symlink(process.execPath, join(bin, 'node'));
  const runtime = await resolveNodeRuntime({ projectDir, execPath: host, versions: { node: '24.0.0' }, isSea: true, path: bin });
  assert.equal(runtime, await realpath(process.execPath));
  await assert.rejects(readFile(entered), error => error.code === 'ENOENT');
}));

test('a PATH runtime with spaces receives no credentials, startup options or host settings', () => fixture(async ({ root, projectDir }) => {
  const bin = join(root, 'runtime with spaces'), captured = join(root, 'probe-environment.json');
  await executable(join(bin, 'node'), `
    require('node:fs').writeFileSync(${JSON.stringify(captured)}, JSON.stringify(process.env));
    const result = require('node:child_process').spawnSync(${JSON.stringify(process.execPath)}, process.argv.slice(2), { env: process.env });
    process.stdout.write(result.stdout); process.exit(result.status ?? 1);
  `);
  const previous = { token: process.env.PREVIEW_RUNTIME_TEST_SECRET, options: process.env.NODE_OPTIONS };
  process.env.PREVIEW_RUNTIME_TEST_SECRET = 'must-stay-in-parent';
  process.env.NODE_OPTIONS = '--require=/missing-startup-hook.cjs';
  try {
    assert.equal(await resolveNodeRuntime({ projectDir, isSea: true, path: bin }), await realpath(process.execPath));
  } finally {
    if (previous.token === undefined) delete process.env.PREVIEW_RUNTIME_TEST_SECRET;
    else process.env.PREVIEW_RUNTIME_TEST_SECRET = previous.token;
    if (previous.options === undefined) delete process.env.NODE_OPTIONS;
    else process.env.NODE_OPTIONS = previous.options;
  }
  const environment = JSON.parse(await readFile(captured, 'utf8'));
  const expected = previewEnvironment(await realpath(join(bin, 'node')));
  assert.equal(environment.PATH, expected.PATH);
  assert.equal(environment.TMPDIR, expected.TMPDIR);
  assert.deepEqual(Object.keys(expected).sort(), ['PATH', 'TMPDIR']);
  assert.equal(environment.PREVIEW_RUNTIME_TEST_SECRET, undefined);
  assert.equal(environment.NODE_OPTIONS, undefined);
}));

test('missing Node gives an actionable error before any room files are created', () => fixture(async ({ projectDir }) => {
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true, path: '' }), error =>
    error.status === 503 && /Node\.js 18 or newer.*PATH/.test(error.message) && /restart the application/.test(error.message));
  assert.deepEqual(await readdir(projectDir), []);
}));

test('project paths, symlinks into the project, empty entries and relative entries cannot supply a runtime', () => fixture(async ({ root, projectDir }) => {
  const entered = join(root, 'project-runtime-entered');
  await executable(join(projectDir, 'node'), `require('node:fs').writeFileSync(${JSON.stringify(entered)}, 'entered');`);
  const linked = join(root, 'linked-project'); await symlink(projectDir, linked);
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true,
    path: ['', '.', 'relative-bin', projectDir, linked].join(delimiter) }), /Node\.js 18 or newer/);
  await assert.rejects(readFile(entered), error => error.code === 'ENOENT');
  assert.deepEqual(await readdir(projectDir), ['node']);
}));

test('dependency folders outside the project, such as a monorepo root, cannot supply a runtime', () => fixture(async ({ root, projectDir }) => {
  const entered = join(root, 'dependency-runtime-entered');
  const dependencies = [join(root, 'node_modules', '.bin'), join(root, 'vendor', 'NODE_MODULES', 'tool', 'bin')];
  for (const bin of dependencies) await executable(join(bin, 'node'), recordingRuntime(entered));
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true, path: dependencies.join(delimiter) }), /Node\.js 18 or newer/);
  await assert.rejects(readFile(entered), error => error.code === 'ENOENT');
  const tools = join(root, 'tools');
  await executable(join(tools, 'node'), recordingRuntime(entered));
  assert.equal(await resolveNodeRuntime({ projectDir, isSea: true, path: [...dependencies, tools].join(delimiter) }),
    await realpath(process.execPath));
  assert.equal(await readFile(entered, 'utf8'), 'x');
}));

test('a runtime that another account can replace is never executed and is named', () => fixture(async ({ root, projectDir }) => {
  const entered = join(root, 'writable-runtime-entered');
  const worldFile = join(root, 'world-writable-file'), worldFolder = join(root, 'world-writable-folder');
  await executable(join(worldFile, 'node'), recordingRuntime(entered));
  await executable(join(worldFolder, 'node'), recordingRuntime(entered));
  await chmod(join(worldFile, 'node'), 0o777);
  await chmod(worldFolder, 0o777);
  const path = [worldFile, worldFolder].join(delimiter);
  const skipped = await realpath(join(worldFile, 'node'));
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true, path }),
    error => /Node\.js 18 or newer/.test(error.message) && error.message.includes(`Skipped ${skipped} because another account can replace it.`));
  await assert.rejects(readFile(entered), error => error.code === 'ENOENT');
  // Group write is normal for private user groups (umask 002) and admin-group prefixes.
  await chmod(worldFolder, 0o775);
  assert.equal(await resolveNodeRuntime({ projectDir, isSea: true, path }), await realpath(process.execPath));
  assert.equal(await readFile(entered, 'utf8'), 'x');
}));

test('a probe cannot nominate a runtime that another account can replace', () => fixture(async ({ root, projectDir }) => {
  const shared = join(root, 'shared'), nominated = join(shared, 'node'), bin = join(root, 'bin');
  await executable(nominated, 'process.exit(1);');
  await executable(join(bin, 'node'), `process.stdout.write(JSON.stringify({ protocol: 'preview-node-runtime-v1',
    version: process.versions.node, executable: ${JSON.stringify(nominated)}, ordinary: true }));`);
  await chmod(shared, 0o777);
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true, path: bin }), /Node\.js 18 or newer/);
  await chmod(shared, 0o755);
  await chmod(nominated, 0o702);
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true, path: bin }), /Node\.js 18 or newer/);
  await chmod(nominated, 0o770);
  assert.equal(await resolveNodeRuntime({ projectDir, isSea: true, path: bin }), await realpath(nominated));
}));

test('invalid and old runtimes are rejected, and duplicate realpaths are probed only once', () => fixture(async ({ root, projectDir }) => {
  const bin = join(root, 'old'), alias = join(root, 'same-old'), attempts = join(root, 'attempts');
  await executable(join(bin, 'node'), `
    require('node:fs').appendFileSync(${JSON.stringify(attempts)}, 'x');
    process.stdout.write(JSON.stringify({ protocol: 'preview-node-runtime-v1', version: '16.0.0',
      executable: process.execPath, ordinary: true }));
  `);
  await symlink(bin, alias);
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true, path: [bin, alias, bin].join(delimiter) }), /Node\.js 18 or newer/);
  assert.equal(await readFile(attempts, 'utf8'), 'x');
}));

test('a runtime probe that hangs is stopped and does not reveal stderr', () => fixture(async ({ root, projectDir }) => {
  const bin = join(root, 'hanging');
  await executable(join(bin, 'node'), "process.stderr.write('private diagnostic'); setInterval(() => {}, 1000);");
  const started = Date.now();
  await assert.rejects(resolveNodeRuntime({ projectDir, isSea: true, path: bin }), error =>
    /Node\.js 18 or newer/.test(error.message) && !error.message.includes('private diagnostic'));
  assert(Date.now() - started < 4000, 'The runtime probe must remain bounded.');
}));
