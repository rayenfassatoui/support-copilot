import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { parseEnv } from 'node:util';

export const root = fileURLToPath(new URL('../', import.meta.url));
export const backend = fileURLToPath(new URL('../backend/', import.meta.url));
export const python = fileURLToPath(new URL('../.venv/bin/python', import.meta.url));

export async function serverEnvironment() {
  let fileValues = {};
  for (const name of ['.env', '.env.local']) {
    try {
      fileValues = parseEnv(await readFile(new URL(`../${name}`, import.meta.url), 'utf8'));
      break;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  return { ...fileValues, ...process.env };
}

export function frontendEnvironment() {
  const values = { ...process.env };
  for (const name of ['DATABASE_URL', 'DATABASE_URL_UNPOOLED', 'MIGRATION_DATABASE_URL', 'OPENROUTER_API_KEY', 'NEON_API_KEY', 'SMTP_PASSWORD', 'SMTP_USERNAME', 'BOOTSTRAP_ADMIN_EMAIL']) {
    delete values[name];
  }
  return values;
}
