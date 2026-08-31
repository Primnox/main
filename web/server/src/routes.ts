/* Route handlers — the coordination plane's surface (CRS/1.0-W §3.2).

   Phase 1: enforce auth, derive identity from the token, drive the event log.
   Every id comes from the client (CRS §1.1) so AAD binding is exact; the server
   validates the shape and relies on primary-key uniqueness. No handler ever
   inspects a payload — the client sends ciphertext, this process stores it.
   State change + its event share one transaction (CRS §4.2). */

import type { FastifyInstance } from 'fastify';
import { requireAuth } from './auth.js';
import { appendEvent, replayAfter, type EventPayload } from './events.js';
import { pool, tx } from './db.js';
import type { SyncQueue } from './sync.js';
import { resolveInstallation } from './github-connection.js';

export interface RouteDeps {
  sync: SyncQueue;
}

const ID = /^[a-z]{2,5}_[0-9a-f-]{8,}$/i;
const badId = (s: unknown): boolean => typeof s !== 'string' || !ID.test(s);

interface StartTurnBody {
  turn_id: string;
  user_message_id: string;
  user_message: EventPayload;
  turn_created_event_id: string;
  turn_created: EventPayload;
  asset_ids?: string[];
  origin_device_id?: string | null;
}

interface PostEventBody {
  event_id: string;
  kind: string;
  turn_id: string;
  conversation_id: string;
  payload: EventPayload;
}

interface CompleteBody {
  conversation_id: string;
  assistant_message_id: string;
  assistant_message: EventPayload;
  completion_event_id: string;
  completion: EventPayload;
}

const ALLOWED_EVENT_KINDS = new Set([
  'token',
  'tool.call',
  'tool.result',
  'permission.request',
  'permission.resolved',
  'turn.failed',
  'turn.cancelled',
  'model.egress',
  'memory.written',
  'workspace.created',
  'workspace.updated',
  'asset.ready',
]);

export function registerRoutes(app: FastifyInstance, deps: RouteDeps): void {
  app.get('/health', async () => ({ ok: true, ts: Date.now() }));

  app.register(async (r) => {
    r.addHook('preHandler', requireAuth);

    // CRS/1.0-W §4.3 — open a new turn; return before any model work.
    r.post<{ Params: { id: string }; Body: StartTurnBody }>(
      '/conversations/:id/turns',
      async (req, reply) => {
        const userId = req.principal!.userId;
        const conversationId = req.params.id;
        const b = req.body;
        if (badId(b.turn_id) || badId(b.user_message_id) || badId(b.turn_created_event_id)) {
          return reply.code(400).send({ error: 'malformed id' });
        }

        const appended = await tx(async (c) => {
          await c.query(
            `INSERT INTO turns (id, conversation_id, user_id, seq_in_conversation, status, origin_device_id)
             VALUES ($1, $2, $3,
               (SELECT COALESCE(MAX(seq_in_conversation), 0) + 1 FROM turns WHERE conversation_id = $2),
               'queued', $4)`,
            [b.turn_id, conversationId, userId, b.origin_device_id ?? null],
          );
          await c.query(
            `INSERT INTO messages (id, turn_id, user_id, role, body_ct)
             VALUES ($1, $2, $3, 'user', $4)`,
            [b.user_message_id, b.turn_id, userId, JSON.stringify(b.user_message)],
          );
          return appendEvent(
            userId,
            {
              eventId: b.turn_created_event_id,
              scope: 'conversation',
              conversationId,
              turnId: b.turn_id,
              kind: 'turn.created',
              payload: b.turn_created,
            },
            c,
          );
        });

        // TODO(§4.4): arm the origin-disconnect watchdog for this turn.
        return reply.code(202).send({ turn_id: b.turn_id, sequence: appended.sequence });
      },
    );

    // CRS/1.0-W §4.3 — the origin client streams events back to the log.
    r.post<{ Params: { id: string }; Body: PostEventBody }>(
      '/turns/:id/events',
      async (req, reply) => {
        const userId = req.principal!.userId;
        const b = req.body;
        if (badId(b.event_id) || badId(b.turn_id)) {
          return reply.code(400).send({ error: 'malformed id' });
        }
        if (!ALLOWED_EVENT_KINDS.has(b.kind)) {
          return reply.code(400).send({ error: `event kind not accepted here: ${b.kind}` });
        }
        const appended = await appendEvent(userId, {
          eventId: b.event_id,
          scope: 'conversation',
          conversationId: b.conversation_id,
          turnId: b.turn_id,
          kind: b.kind,
          payload: b.payload,
        });
        return reply.send({ sequence: appended.sequence });
      },
    );

    // CRS/1.0-W §4.3 — finalize.
    r.post<{ Params: { id: string }; Body: CompleteBody }>(
      '/turns/:id/complete',
      async (req, reply) => {
        const userId = req.principal!.userId;
        const turnId = req.params.id;
        const b = req.body;
        if (badId(turnId) || badId(b.assistant_message_id) || badId(b.completion_event_id)) {
          return reply.code(400).send({ error: 'malformed id' });
        }

        const appended = await tx(async (c) => {
          await c.query(
            `UPDATE turns SET status = 'completed', completed_at = now()
             WHERE id = $1 AND user_id = $2`,
            [turnId, userId],
          );
          await c.query(
            `INSERT INTO messages (id, turn_id, user_id, role, body_ct)
             VALUES ($1, $2, $3, 'assistant', $4)`,
            [b.assistant_message_id, turnId, userId, JSON.stringify(b.assistant_message)],
          );
          return appendEvent(
            userId,
            {
              eventId: b.completion_event_id,
              scope: 'conversation',
              conversationId: b.conversation_id,
              turnId,
              kind: 'turn.completed',
              payload: b.completion,
            },
            c,
          );
        });

        deps.sync.schedule(userId); // §W2 — debounced encrypted mirror to the user's repo
        return reply.send({ sequence: appended.sequence });
      },
    );

    // CRS §9 — cancellation (idempotent, §9.1.2).
    r.delete<{ Params: { id: string } }>('/turns/:id', async (req, reply) => {
      const userId = req.principal!.userId;
      const turnId = req.params.id;
      await tx(async (c) => {
        await c.query(
          `UPDATE turns SET status = 'cancelled'
           WHERE id = $1 AND user_id = $2 AND status NOT IN ('completed','failed','cancelled')`,
          [turnId, userId],
        );
        await c.query(
          `UPDATE jobs SET cancel_requested = true
           WHERE turn_id = $1 AND status IN ('queued','running')`,
          [turnId],
        );
      });
      return reply.send({ ok: true });
    });

    // CRS §8.1 — reconnect replay. `after` is last_event_seen.
    r.get<{ Querystring: { after?: string } }>('/replay', async (req, reply) => {
      const userId = req.principal!.userId;
      const after = Number(req.query.after ?? 0);
      const events = await replayAfter(userId, Number.isFinite(after) ? after : 0);
      const head = events.length ? Number(events[events.length - 1]!.sequence) : after;
      return reply.send({ events, sync: { head } });
    });

    // CRS/1.0-W §5, §W1 — the sealed vault blob. All fields are ciphertext or
    // non-secret metadata; the server cannot derive a key from any of it.
    r.get('/vault', async (req, reply) => {
      const userId = req.principal!.userId;
      const { rows } = await pool.query(
        `SELECT kdf, wrapped_dek, wrapped_dek_recovery, recovery_salt_b64, keys_ct, key_version
           FROM vault WHERE user_id = $1`,
        [userId],
      );
      return reply.send(rows[0] ?? null);
    });

    r.put<{
      Body: {
        kdf: unknown;
        wrapped_dek: unknown;
        wrapped_dek_recovery?: unknown;
        recovery_salt_b64?: string | null;
        keys_ct?: unknown;
        key_version: number;
      };
    }>('/vault', async (req, reply) => {
      const userId = req.principal!.userId;
      const b = req.body;
      if (!b.kdf || !b.wrapped_dek || typeof b.key_version !== 'number') {
        return reply.code(400).send({ error: 'incomplete vault blob' });
      }
      await pool.query(
        `INSERT INTO vault (user_id, kdf, wrapped_dek, wrapped_dek_recovery, recovery_salt_b64, keys_ct, key_version, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, now())
         ON CONFLICT (user_id) DO UPDATE
           SET kdf = EXCLUDED.kdf,
               wrapped_dek = EXCLUDED.wrapped_dek,
               wrapped_dek_recovery = EXCLUDED.wrapped_dek_recovery,
               recovery_salt_b64 = EXCLUDED.recovery_salt_b64,
               keys_ct = COALESCE(EXCLUDED.keys_ct, vault.keys_ct),
               key_version = EXCLUDED.key_version,
               updated_at = now()`,
        [
          userId,
          JSON.stringify(b.kdf),
          JSON.stringify(b.wrapped_dek),
          b.wrapped_dek_recovery ? JSON.stringify(b.wrapped_dek_recovery) : null,
          b.recovery_salt_b64 ?? null,
          b.keys_ct ? JSON.stringify(b.keys_ct) : null,
          b.key_version,
        ],
      );
      return reply.send({ ok: true });
    });

    // CRS/1.0-W §8, §W2 — record a GitHub App installation for this user.
    r.post<{ Body: { installation_id: string } }>('/github/connect', async (req, reply) => {
      const userId = req.principal!.userId;
      const installationId = String(req.body.installation_id ?? '');
      if (!/^\d+$/.test(installationId)) {
        return reply.code(400).send({ error: 'installation_id must be numeric' });
      }
      let repoFullName: string;
      let repoId: number;
      try {
        ({ repoFullName, repoId } = await resolveInstallation(installationId));
      } catch (e) {
        return reply.code(400).send({ error: (e as Error).message });
      }
      await pool.query(
        `INSERT INTO github_connection (user_id, installation_id, repo_id, repo_full_name, status)
         VALUES ($1, $2, $3, $4, 'connected')
         ON CONFLICT (user_id) DO UPDATE
           SET installation_id = EXCLUDED.installation_id,
               repo_id = EXCLUDED.repo_id,
               repo_full_name = EXCLUDED.repo_full_name,
               status = 'connected',
               connected_at = now()`,
        [userId, installationId, String(repoId), repoFullName],
      );
      return reply.send({ connected: true, repo_full_name: repoFullName });
    });

    r.post('/github/disconnect', async (req, reply) => {
      const userId = req.principal!.userId;
      await pool.query(`DELETE FROM github_connection WHERE user_id = $1`, [userId]);
      return reply.send({ connected: false });
    });

    r.get('/github/status', async (req, reply) => {
      const userId = req.principal!.userId;
      const { rows } = await pool.query<{ repo_full_name: string | null; status: string }>(
        `SELECT repo_full_name, status FROM github_connection WHERE user_id = $1`,
        [userId],
      );
      return reply.send(rows[0] ?? { status: 'disconnected', repo_full_name: null });
    });
  });
}
