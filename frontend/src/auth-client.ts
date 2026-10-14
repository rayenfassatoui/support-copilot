import { createAuthClient, type ReactBetterAuthClient } from '@neondatabase/auth';
import { BetterAuthReactAdapter } from '@neondatabase/auth/react/adapters';

let clientPromise: Promise<ReactBetterAuthClient> | null = null;
let tokenPromise: Promise<string> | null = null;
let cachedToken: { value: string; expiresAt: number } | null = null;
let tokenGeneration = 0;

export class SessionRequiredError extends Error {}

export function getAuthClient(): Promise<ReactBetterAuthClient> {
  if (!clientPromise) {
    clientPromise = fetch('/api/auth/config', { headers: { Accept: 'application/json' } })
      .then(async response => {
        if (!response.ok) throw new Error('Authentication service is unavailable.');
        const config = await response.json() as { auth_url: string | null; configured: boolean };
        if (!config.configured || !config.auth_url) throw new Error('Authentication is not configured on the server.');
        return createAuthClient(config.auth_url, { adapter: BetterAuthReactAdapter({ fetchOptions: { credentials: 'include' } }) });
      }).catch(error => { clientPromise = null; throw error; });
  }
  return clientPromise;
}

export function clearAuthToken() {
  tokenGeneration += 1;
  cachedToken = null;
  tokenPromise = null;
}

export async function getBearerToken(): Promise<string> {
  if (cachedToken && cachedToken.expiresAt > Date.now() + 60000) return cachedToken.value;
  if (!tokenPromise) {
    const generation = tokenGeneration;
    tokenPromise = (async () => {
      const client = await getAuthClient();
      // Neon injects the API JWT into session.token; /token can return that same cached session object.
      const result = await client.getSession();
      if (result.error?.status === 401 || (!result.error && !result.data?.session)) throw new SessionRequiredError('Sign in to continue.');
      if (result.error || !result.data?.session?.token) throw new Error('Authentication service is unavailable.');
      const token = result.data.session.token;
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) as { exp: number };
      if (!Number.isFinite(payload.exp)) throw new Error('The authentication service returned an invalid session.');
      if (generation !== tokenGeneration) throw new Error('The active session changed.');
      cachedToken = { value: token, expiresAt: payload.exp * 1000 };
      return token;
    })().finally(() => { if (generation === tokenGeneration) tokenPromise = null; });
  }
  return tokenPromise;
}
