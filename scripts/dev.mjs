import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const common = { cwd: root, stdio: 'inherit', env: process.env, windowsHide: false };

const api = spawn(process.execPath, [path.join(root, 'backend', 'server.mjs')], common);

// On Windows, invoking npm.cmd directly can throw spawn EINVAL on some Node 22
// installations. Launching it through the system command processor is reliable.
const web = process.platform === 'win32'
  ? spawn(process.env.ComSpec || 'C:\\Windows\\System32\\cmd.exe', ['/d', '/s', '/c', 'npm run dev:web'], common)
  : spawn('npm', ['run', 'dev:web'], common);

const children = [api, web];
let stopping = false;

function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (!child.killed) child.kill(process.platform === 'win32' ? undefined : 'SIGTERM');
  }
  setTimeout(() => process.exit(exitCode), 100).unref();
}

for (const [name, child] of [['API', api], ['Web', web]]) {
  child.on('error', (error) => {
    console.error(`\nClipperX ${name} process could not start:`, error.message);
    stop(1);
  });
  child.on('exit', (code, signal) => {
    if (!stopping && code !== 0) {
      console.error(`\nClipperX ${name} process exited (${code ?? signal}).`);
      stop(code || 1);
    }
  });
}

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
process.on('exit', () => {
  for (const child of children) if (!child.killed) child.kill();
});
