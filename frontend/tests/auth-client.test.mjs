import assert from 'node:assert/strict';
import { generateKeyPairSync, sign, verify } from 'node:crypto';
import test from 'node:test';
import { clearAuthToken, getAuthClient, getBearerToken, SessionRequiredError } from '../src/auth-client.ts';

test('a restored Neon session authorizes API access until sign-out', async (context) => {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519');
  const header = Buffer.from(JSON.stringify({ alg: 'EdDSA', kid: 'session-regression' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({ sub: 'synthetic-user', exp: Math.floor(Date.now() / 1000) + 900 })).toString('base64url');
  const signed = `${header}.${payload}`;
  const jwt = `${signed}.${sign(null, Buffer.from(signed), privateKey).toString('base64url')}`;
  let signedIn = true;
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; clearAuthToken(); });
  // Keep the installed Neon adapter and its session cache real; control only its HTTP boundary.
  globalThis.fetch = async input => {
    const url = String(input);
    if (url === '/api/auth/config') return Response.json({ configured: true, auth_url: 'https://auth.example.com/auth' });
    if (url.endsWith('/sign-out')) {
      signedIn = false;
      return Response.json({ success: true });
    }
    if (url.includes('/get-session')) return signedIn ? Response.json({
      user: { id: 'synthetic-user', email: 'synthetic@example.com' },
      session: { token: 'opaque-cookie-session', expiresAt: new Date(Date.now() + 86400000).toISOString() },
    }, { headers: { 'set-auth-jwt': jwt } }) : Response.json(null);
    if (url.endsWith('/token')) return signedIn ? Response.json({ token: jwt }) : Response.json({ code: 'UNAUTHORIZED' }, { status: 401 });
    throw new Error(`Unexpected authentication endpoint: ${url}`);
  };

  const client = await getAuthClient();
  await client.getSession(); // AuthProvider restores the session before its first protected API request.
  clearAuthToken();
  const bearer = await getBearerToken();
  const [encodedHeader, encodedPayload, signature] = bearer.split('.');
  assert.ok(verify(null, Buffer.from(`${encodedHeader}.${encodedPayload}`), publicKey, Buffer.from(signature, 'base64url')),
    'A restored session must supply a signed API JWT, not the opaque session-cookie token.');

  await client.signOut();
  clearAuthToken();
  await assert.rejects(getBearerToken(), SessionRequiredError);
});
