import { spawn } from 'node:child_process';
import { backend, python, serverEnvironment } from './api-env.mjs';

if (process.argv.length < 3) {
  console.error('Usage: npm run api -- -m app.seed (or another Python backend command).');
  process.exitCode = 1;
} else {
  const child = spawn(python, process.argv.slice(2), {
    cwd: backend,
    env: await serverEnvironment(),
    stdio: 'inherit',
  });
  child.on('error', () => {
    console.error('Cannot start backend Python. Create the root .venv with Python 3.12 and install backend/requirements-test.txt.');
    process.exitCode = 1;
  });
  child.on('exit', (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
}
