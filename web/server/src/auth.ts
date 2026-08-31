/* Supabase JWT verification (ARCH §13 equivalent).

   The user id is ALWAYS derived from the verified token's `sub`, never from a
   request body or query param — a client claiming `user_id: "someone-else"` is
   ignored. */

import { createRemoteJWKSet, jwtVerify } from 'jose';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { config } from './config.js';

const jwks = createRemoteJWKSet(new URL(config.supabaseJwksUrl));

export interface Principal {
  userId: string;
  sessionId?: string;
}

declare module 'fastify' {
  interface FastifyRequest {
    principal?: Principal;
  }
}

export async function verifyBearer(token: string): Promise<Principal> {
  const { payload } = await jwtVerify(token, jwks, {
    issuer: config.supabaseJwtIss || undefined,
    // Supabase access tokens use aud "authenticated"
    audience: 'authenticated',
  });
  if (!payload.sub) throw new Error('token has no sub');
  return { userId: payload.sub, sessionId: typeof payload.session_id === 'string' ? payload.session_id : undefined };
}

/** Fastify preHandler — 401 unless a valid bearer token is present. */
export async function requireAuth(req: FastifyRequest, reply: FastifyReply): Promise<void> {
  const h = req.headers.authorization;
  if (!h?.startsWith('Bearer ')) {
    await reply.code(401).send({ error: 'missing bearer token' });
    return;
  }
  try {
    req.principal = await verifyBearer(h.slice(7));
  } catch (e) {
    req.log.warn({ err: (e as Error).message }, 'jwt verify failed');
    await reply.code(401).send({ error: 'invalid token' });
  }
}
