/* The turn driver (CRS/1.0-W §4.3, §4.4).

   The browser owns a turn end to end: generate the ids, seal the user message,
   open the turn on Render, build the context bundle locally, stream from the
   provider, seal + POST each token before treating it as committed, then seal
   the assistant message and complete the turn. Render only ever receives
   ciphertext + envelope facts.

   Abort (`signal`) is the local half of cancellation: post `turn.cancelled`
   with the partial text (CRS §9.3), then DELETE the turn. */

import { type Sealed, seal, utf8 } from '../crypto';
import { aadFor } from '../crypto/aad';
import { newId } from '../ids';
import type { ModelProfile, ModelRouter } from '../model';
import { buildBundle, type BundleInput } from '../context/bundle';
import { sealEventPayload } from './eventcodec';
import type { Transport } from './transport';

export interface RunTurnDeps {
  router: ModelRouter;
  transport: Transport;
  dek: CryptoKey;
  profile: ModelProfile;
  originDeviceId?: string;
  onEvent?: (e: LocalTurnEvent) => void;
}

export type LocalTurnEvent =
  | { type: 'status'; status: TurnPhase }
  | { type: 'token'; text: string }
  | { type: 'done'; text: string; usage: { input: number; output: number } }
  | { type: 'cancelled'; text: string }
  | { type: 'error'; code: string; message: string; retryable: boolean };

export type TurnPhase = 'building_context' | 'thinking' | 'streaming';

export interface RunTurnInput {
  conversationId: string;
  userText: string;
  context: Omit<BundleInput, 'userText'>;
  signal?: AbortSignal;
  /** called once the turn id exists — lets the caller register a cancel handle */
  onStart?: (turnId: string) => void;
}

export type RunTurnResult =
  | { ok: true; turnId: string; text: string; usage: { input: number; output: number } }
  | {
      ok: false;
      turnId: string;
      cancelled?: true;
      error?: { code: string; message: string; retryable: boolean };
    };

const sealMessage = (dek: CryptoKey, msgId: string, text: string): Promise<Sealed> =>
  seal(dek, utf8(JSON.stringify({ text })), utf8(aadFor.message(msgId)));

export async function runTurn(deps: RunTurnDeps, input: RunTurnInput): Promise<RunTurnResult> {
  const { router, transport, dek, profile } = deps;
  const emit = (e: LocalTurnEvent) => deps.onEvent?.(e);

  // §4.6 — do not open a turn we cannot run.
  if (!profile.apiKey) {
    const err = { code: 'provider_auth', message: 'no API key unlocked for this provider', retryable: false };
    emit({ type: 'error', ...err });
    return { ok: false, turnId: '', error: err };
  }

  const turnId = newId('turn');
  const userMsgId = newId('msg');
  const turnCreatedEventId = newId('evt');

  const userMessage = await sealMessage(dek, userMsgId, input.userText);
  const turnCreated = await sealEventPayload(dek, turnCreatedEventId, 'turn.created', {
    turn: { id: turnId },
    user_text: input.userText,
  });

  await transport.startTurn({
    turnId,
    conversationId: input.conversationId,
    userMessageId: userMsgId,
    userMessage,
    turnCreatedEventId,
    turnCreated,
    originDeviceId: deps.originDeviceId,
  });
  input.onStart?.(turnId);

  emit({ type: 'status', status: 'building_context' });
  const bundle = buildBundle({ ...input.context, userText: input.userText });

  emit({ type: 'status', status: 'thinking' });
  let text = '';
  let usage = { input: 0, output: 0 };
  let sawToken = false;

  const postEvent = (kind: string, payload: unknown) => {
    const eventId = newId('evt');
    return sealEventPayload(dek, eventId, kind, payload).then((sealed) =>
      transport.postEvent({
        eventId,
        turnId,
        conversationId: input.conversationId,
        kind,
        payload: sealed,
      }),
    );
  };

  try {
    for await (const ev of router.stream(
      { system: bundle.system, messages: bundle.messages, profile, signal: input.signal },
      {
        onEgress: (fact) => {
          void postEvent('model.egress', {
            provider: fact.provider,
            model: fact.model,
            input_tokens: fact.approxInputTokens,
          }).catch(() => undefined);
        },
      },
    )) {
      if (input.signal?.aborted) break;

      if (ev.type === 'token') {
        if (!sawToken) {
          sawToken = true;
          emit({ type: 'status', status: 'streaming' });
        }
        text += ev.text;
        emit({ type: 'token', text: ev.text });
        await postEvent('token', { text: ev.text }); // committed before render is final (§4.3)
      } else if (ev.type === 'usage') {
        usage = { input: ev.inputTokens, output: ev.outputTokens };
      } else if (ev.type === 'error') {
        if (ev.code === 'cancelled_by_user') break;
        await postEvent('turn.failed', {
          code: ev.code,
          message: ev.message,
          retryable: ev.retryable,
        }).catch(() => undefined);
        emit({ type: 'error', code: ev.code, message: ev.message, retryable: ev.retryable });
        return { ok: false, turnId, error: { code: ev.code, message: ev.message, retryable: ev.retryable } };
      }
    }
  } catch (e) {
    if (!isAbort(e)) {
      const msg = e instanceof Error ? e.message : String(e);
      await postEvent('turn.failed', { code: 'internal', message: msg, retryable: true }).catch(
        () => undefined,
      );
      emit({ type: 'error', code: 'internal', message: msg, retryable: true });
      return { ok: false, turnId, error: { code: 'internal', message: msg, retryable: true } };
    }
  }

  if (input.signal?.aborted) {
    await postEvent('turn.cancelled', { partial_text: text }).catch(() => undefined);
    await transport.cancelTurn(turnId).catch(() => undefined);
    emit({ type: 'cancelled', text });
    return { ok: false, turnId, cancelled: true };
  }

  const asstMsgId = newId('msg');
  const completionEventId = newId('evt');
  const assistantMessage = await sealMessage(dek, asstMsgId, text);
  const completion = await sealEventPayload(dek, completionEventId, 'turn.completed', {
    assistant_text: text,
    usage: { input_tokens: usage.input, output_tokens: usage.output },
  });

  await transport.completeTurn({
    turnId,
    conversationId: input.conversationId,
    assistantMessageId: asstMsgId,
    assistantMessage,
    completionEventId,
    completion,
  });

  emit({ type: 'done', text, usage });
  return { ok: true, turnId, text, usage };
}

function isAbort(e: unknown): boolean {
  return e instanceof Error && (e.name === 'AbortError' || e.message === 'aborted');
}
