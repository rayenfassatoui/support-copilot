import { spawn } from 'node:child_process';
import { access } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';
import { backend, python, root, serverEnvironment, frontendEnvironment } from './api-env.mjs';

const children = new Set();
let stopping = false;
function stop(code) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) child.kill('SIGTERM');
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => stop(0));

function launch(binary, args, cwd, env) {
  const child = spawn(binary, args, { cwd, env, stdio: 'inherit' });
  children.add(child);
  return new Promise((resolve, reject) => {
    child.once('error', () => { children.delete(child); reject(new Error('Unable to start an app process. Check the Python 3.12 virtualenv and frontend dependencies.')); });
    child.once('spawn', () => resolve(child));
    child.once('exit', (code, signal) => {
      children.delete(child);
      if (child.appService && !stopping) {
        console.error(`App service exited (${code ?? signal}).`);
        stop(code || 1);
      }
    });
  });
}

async function runPython(args, env) {
  const child = await launch(python, args, backend, env);
  const result = await new Promise(resolve => child.once('exit', code => resolve(code)));
  if (result !== 0) throw new Error(`Backend setup command failed (${result}). App not started.`);
}

try {
  await access(new URL('../frontend/dist/index.html', import.meta.url));
  const env = await serverEnvironment();
  await runPython(['-m', 'app.tokenization'], env);
  await runPython(['-m', 'alembic', 'upgrade', 'head'], env);
  const api = await launch(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], backend, env);
  api.appService = true;
  let ready = false;
  for (let attempt = 0; attempt < 60 && api.exitCode === null; attempt += 1) {
    try {
      const response = await fetch('http://127.0.0.1:8000/openapi.json', { signal: AbortSignal.timeout(1000) });
      if (response.ok) { ready = true; break; }
    } catch {}
    await delay(250);
  }
  if (!ready) throw new Error('API did not start on loopback port 8000.');
  const web = await launch('npm', ['--prefix', 'frontend', 'run', 'preview', '--', '--host', '127.0.0.1', '--port', '8080', '--strictPort'], root, frontendEnvironment());
  web.appService = true;
  console.log('Support Copilot: http://127.0.0.1:8080 | API: http://127.0.0.1:8000/docs');
} catch (error) {
  console.error(error.code === 'ENOENT' ? 'Run npm run build before npm start, and create the Python 3.12 .venv.' : error.message);
  stop(1);
}
