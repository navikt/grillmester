import { execFile } from 'node:child_process';
import { access, realpath, stat } from 'node:fs/promises';
import { constants } from 'node:fs';
import { delimiter, dirname, isAbsolute, join, relative, sep } from 'node:path';
import { tmpdir } from 'node:os';

const unavailable = () => Object.assign(new Error('Designverksted needs Node.js 18 or newer on the application PATH. Make Node.js available and restart the application.'), { status: 503 });
const outside = (project, filename) => {
  const path = relative(project, filename);
  return path === '..' || path.startsWith(`..${sep}`) || isAbsolute(path);
};

export function previewEnvironment(executable) {
  return { PATH: dirname(executable), TMPDIR: tmpdir() };
}

async function bundledRuntime() {
  // node:sea was added after Node 18, which remains a supported server runtime.
  try { return (await import('node:sea')).isSea(); }
  catch { return false; }
}

const probe = `
let sea = false;
try { sea = require('node:sea').isSea(); } catch {}
process.stdout.write(JSON.stringify({ protocol: 'preview-node-runtime-v1',
  version: process.versions.node, executable: process.execPath,
  ordinary: !sea && !process.versions.bun && !process.versions.electron }));
`;

async function inspect(executable, timeout) {
  return new Promise(resolve => {
    execFile(executable, ['--eval', probe], {
      cwd: dirname(executable), env: previewEnvironment(executable),
      timeout, killSignal: 'SIGKILL', maxBuffer: 4096, windowsHide: true,
    }, (error, stdout) => {
      if (error) return resolve(null);
      try {
        const value = JSON.parse(stdout);
        if (value.protocol !== 'preview-node-runtime-v1' || value.ordinary !== true
            || typeof value.version !== 'string' || !/^\d+\.\d+\.\d+(?:[-+].*)?$/.test(value.version)
            || Number(value.version.split('.')[0]) < 18
            || typeof value.executable !== 'string' || !isAbsolute(value.executable)) return resolve(null);
        resolve(value.executable);
      } catch { resolve(null); }
    });
  });
}

// A packaged application's executable can contain Node without accepting Node
// script arguments. Resolve an ordinary runtime before creating any room files.
export async function resolveNodeRuntime({ projectDir, path = process.env.PATH || '',
  execPath = process.execPath, versions = process.versions, isSea } = {}) {
  let project;
  try { project = await realpath(projectDir); } catch { throw unavailable(); }
  const embedded = isSea === undefined ? await bundledRuntime() : isSea;
  const candidates = [];
  if (!embedded && !versions.bun && !versions.electron && versions.node) candidates.push(execPath);
  for (const directory of path.split(delimiter)) {
    if (isAbsolute(directory) && outside(project, directory)) {
      candidates.push(join(directory, process.platform === 'win32' ? 'node.exe' : 'node'));
    }
  }
  const seen = new Set(), deadline = Date.now() + 5000;
  for (const candidate of candidates) {
    if (!isAbsolute(candidate) || Date.now() >= deadline || seen.size >= 32) continue;
    let executable;
    try {
      executable = await realpath(candidate);
      if (seen.has(executable) || !outside(project, executable)) continue;
      seen.add(executable);
      if (!(await stat(executable)).isFile()) continue;
      await access(executable, constants.X_OK);
      const reported = await inspect(executable, Math.max(1, Math.min(1000, deadline - Date.now())));
      if (!reported) continue;
      const resolved = await realpath(reported);
      if (!outside(project, resolved) || !(await stat(resolved)).isFile()) continue;
      await access(resolved, constants.X_OK);
      return resolved;
    } catch { /* An unavailable candidate must not expose its stderr or environment. */ }
  }
  throw unavailable();
}
