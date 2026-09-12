import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const production = process.argv.includes('--production');
const children = [];
let closing = false;
function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      stdio: 'inherit',
      ...options,
    });
    child.on('error', reject);
    child.on('exit', (code) =>
      code === 0 ? resolve() : reject(new Error(`${command} exited ${code}`)),
    );
  });
}
async function probe(url) {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(3000) })).ok;
  } catch {
    return false;
  }
}
function stop() {
  if (closing) return;
  closing = true;
  for (const child of children) child.kill('SIGTERM');
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
function start(command, args) {
  const child = spawn(command, args, { cwd: root, stdio: 'inherit' });
  children.push(child);
  child.on('error', (error) => {
    console.error(error.message);
    stop();
    process.exitCode = 1;
  });
  child.on('exit', (code) => {
    if (!closing) {
      process.exitCode = code || 1;
      stop();
    }
  });
}
try {
  if (await probe('http://127.0.0.1:3000/'))
    throw new Error('3000 端口已有服务。请先停止已有演示，避免启动重复实例。');
  if (await probe('http://127.0.0.1:8000/api/health'))
    throw new Error('8000 端口已有 HR 服务。请先停止已有演示。');
  const uv = existsSync(join(homedir(), '.local/bin/uv'))
    ? join(homedir(), '.local/bin/uv')
    : 'uv';
  if (!existsSync(join(root, '.venv'))) await run(uv, ['sync', '--frozen']);
  if (!existsSync(join(root, 'node_modules'))) await run('npm', ['ci']);
  if (!existsSync(join(root, 'data/hr.sqlite')))
    await run(uv, ['run', 'python', '-m', 'backend.hr.seed']);
  const lms = existsSync(join(homedir(), '.lmstudio/bin/lms'))
    ? join(homedir(), '.lmstudio/bin/lms')
    : 'lms';
  if (!(await probe('http://127.0.0.1:1234/v1/models')))
    await run(lms, [
      'server',
      'start',
      '--port',
      '1234',
      '--bind',
      '127.0.0.1',
    ]);
  const models = await (await fetch('http://127.0.0.1:1234/v1/models')).json();
  if (
    !models.data?.some(
      (m) => m.id === (process.env.LM_STUDIO_MODEL || 'hr-qwen'),
    )
  )
    await run(lms, [
      'load',
      'qwen3.8-27b-mlx',
      '--identifier',
      'hr-qwen',
      '--context-length',
      '8192',
      '--yes',
    ]);
  if (production && !existsSync(join(root, 'dist/server')))
    await run('npm', ['run', 'build']);
  start(uv, [
    'run',
    'uvicorn',
    'backend.hr.api:app',
    '--host',
    '127.0.0.1',
    '--port',
    '8000',
  ]);
  start('npm', ['run', production ? 'start' : 'dev']);
  console.log(
    '\n澄观 HR 演示：http://127.0.0.1:3000/\n按 Ctrl+C 停止本次启动的前后端；保留 LM Studio 服务。\n',
  );
} catch (error) {
  console.error(error.message);
  stop();
  process.exitCode = 1;
}
