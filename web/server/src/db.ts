import pg from 'pg';
import { config } from './config.js';

/* Service-role pool. RLS is bypassed here by design: this process assigns the
   one global sequence and appends events (CRS §3.1, §4.2). It reads no payload
   plaintext — payloads are opaque ciphertext. */
export const pool = new pg.Pool({
  connectionString: config.databaseUrl,
  max: 10,
  idleTimeoutMillis: 30_000,
});

export type Client = pg.PoolClient;

/** Run `fn` inside a single transaction, rolling back on any throw. */
export async function tx<T>(fn: (c: Client) => Promise<T>): Promise<T> {
  const c = await pool.connect();
  try {
    await c.query('BEGIN');
    const out = await fn(c);
    await c.query('COMMIT');
    return out;
  } catch (e) {
    try {
      await c.query('ROLLBACK');
    } catch {
      /* connection already broken */
    }
    throw e;
  } finally {
    c.release();
  }
}
