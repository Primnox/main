/* Primnox Web — the coordination plane (CRS/1.0-W §3.2).

   Not an orchestrator. It verifies identity, assigns the one global event
   sequence, appends ciphertext to the log, keeps turn/job lifecycle rows, holds
   the GitHub App key for the encrypted sync job, and runs the origin-disconnect
   watchdog. It never sees a plaintext prompt, memory, message, or key. */

import Fastify, { type FastifyError } from 'fastify';
import { config } from './config.js';
import { registerRoutes } from './routes.js';
import { pool } from './db.js';
import { startWatchdog } from './watchdog.js';
import { SyncQueue, type PendingRow } from './sync.js';
import { githubClientFor } from './github-connection.js';

const app = Fastify({
  logger: { level: process.env.LOG_LEVEL ?? 'info' },
  bodyLimit: 2 * 1024 * 1024,
});

// minimal CORS for the SPA origin — no credentials, JSON only
app.addHook('onRequest', async (req, reply) => {
  reply.header('access-control-allow-origin', config.clientOrigin);
  reply.header('access-control-allow-headers', 'authorization,content-type');
  reply.header('access-control-allow-methods', 'GET,POST,DELETE,OPTIONS');
  if (req.method === 'OPTIONS') reply.code(204).send();
});

const sync = new SyncQueue({
  debounceMs: config.syncDebounceMs,
  githubFor: (userId) => githubClientFor(userId).catch(() => null),
  readLastSynced: async (userId) => {
    const { rows } = await pool.query<{ last_synced_seq: string }>(
      `SELECT last_synced_seq FROM sync_state WHERE user_id = $1`,
      [userId],
    );
    return rows[0] ? Number(rows[0].last_synced_seq) : 0;
  },
  loadPending: async (userId, afterSeq) => {
    const { rows } = await pool.query<PendingRow>(
      `SELECT event_id, sequence, ts, scope, conversation_id, turn_id, kind, payload_ct
         FROM events WHERE user_id = $1 AND sequence > $2 ORDER BY sequence ASC LIMIT 5000`,
      [userId, afterSeq],
    );
    const head = rows.length ? Number(rows[rows.length - 1]!.sequence) : afterSeq;
    return { rows, head };
  },
  writeState: async (userId, head, repoHead) => {
    await pool.query(
      `INSERT INTO sync_state (user_id, repo_head, last_synced_seq, updated_at)
       VALUES ($1, $2, $3, now())
       ON CONFLICT (user_id) DO UPDATE
         SET repo_head = EXCLUDED.repo_head,
             last_synced_seq = EXCLUDED.last_synced_seq,
             updated_at = now()`,
      [userId, repoHead, head],
    );
  },
  log: (msg, extra) => app.log.info({ extra }, `[sync] ${msg}`),
});

registerRoutes(app, { sync });

app.setErrorHandler((err: FastifyError, req, reply) => {
  req.log.error({ err }, 'request failed');
  const status = err.statusCode ?? 500;
  reply.code(status).send({ error: status === 500 ? 'internal' : err.message });
});

async function main() {
  await pool.query('SELECT 1'); // fail fast if the DB is unreachable
  const watchdog = startWatchdog(config.originGraceSeconds);

  const shutdown = async () => {
    watchdog.stop();
    await app.close();
    await pool.end();
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);

  await app.listen({ port: config.port, host: '0.0.0.0' });
  app.log.info(`primnox-web coordination plane on :${config.port}`);
}

main().catch((e) => {
  app.log.error(e);
  process.exit(1);
});
