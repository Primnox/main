/* The Model Router (CRS/1.0-W §10).

   Picks a provider adapter and yields normalized StreamEvents. It also emits
   the `model.egress` audit fact (counts, no content — §4.6) via the optional
   `onEgress` hook so the turn driver can log it to the event stream. */

import { providers as defaultProviders } from './providers';
import { resolveCapabilities } from './capabilities';
import { ModelRequest, Provider, ProviderId, StreamEvent } from './types';

export interface RouterOptions {
  providers?: Record<ProviderId, Provider>;
  /** called once per request, before the first token, with the outbound fact */
  onEgress?: (fact: { provider: ProviderId; model: string; approxInputTokens: number }) => void;
}

export class ModelRouter {
  private readonly providers: Record<ProviderId, Provider>;
  private readonly onEgress?: RouterOptions['onEgress'];

  constructor(opts: RouterOptions = {}) {
    this.providers = opts.providers ?? defaultProviders;
    this.onEgress = opts.onEgress;
  }

  capabilitiesFor(provider: ProviderId, model: string) {
    return resolveCapabilities(provider, model);
  }

  async *stream(
    req: ModelRequest,
    hooks?: { onEgress?: RouterOptions['onEgress'] },
  ): AsyncGenerator<StreamEvent> {
    const p = this.providers[req.profile.provider];
    if (!p) {
      yield {
        type: 'error',
        code: 'model_unavailable',
        message: `no adapter for provider "${req.profile.provider}"`,
        retryable: false,
      };
      return;
    }
    if (!req.profile.apiKey) {
      yield {
        type: 'error',
        code: 'provider_auth',
        message: 'no API key unlocked for this provider',
        retryable: false,
      };
      return;
    }

    (hooks?.onEgress ?? this.onEgress)?.({
      provider: req.profile.provider,
      model: req.profile.model,
      approxInputTokens: approxTokens(req),
    });

    yield* p.stream(req);
  }
}

/** ~4 chars per token — good enough for an egress estimate and a budget guard. */
export function approxTokens(req: Pick<ModelRequest, 'system' | 'messages'>): number {
  let chars = req.system?.length ?? 0;
  for (const m of req.messages) chars += m.content.length + 4;
  return Math.ceil(chars / 4);
}
