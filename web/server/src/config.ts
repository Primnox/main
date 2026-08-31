/* Env parsing. Fails fast on a missing required value rather than 500-ing at
   request time. */

function req(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`missing required env: ${name}`);
  return v;
}

function num(name: string, fallback: number): number {
  const v = process.env[name];
  if (v === undefined) return fallback;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`env ${name} is not a number: ${v}`);
  return n;
}

// A GitHub App private key pasted into an env var keeps its newlines as "\n".
const pem = (v: string | undefined): string => (v ? v.replace(/\\n/g, '\n') : '');

export const config = {
  port: num('PORT', 8787),
  databaseUrl: req('DATABASE_URL'),
  supabaseJwksUrl: req('SUPABASE_JWKS_URL'),
  supabaseJwtIss: process.env.SUPABASE_JWT_ISS ?? '',
  originGraceSeconds: num('ORIGIN_GRACE_SECONDS', 45),
  rateLimitPerMin: num('RATE_LIMIT_PER_MIN', 120),
  syncDebounceMs: num('SYNC_DEBOUNCE_MS', 5000),
  clientOrigin: process.env.CLIENT_ORIGIN ?? '*',
  githubAppId: process.env.GITHUB_APP_ID ?? '',
  githubAppPrivateKey: pem(process.env.GITHUB_APP_PRIVATE_KEY),
  githubAppClientId: process.env.GITHUB_APP_CLIENT_ID ?? '',
  githubAppClientSecret: process.env.GITHUB_APP_CLIENT_SECRET ?? '',
} as const;
