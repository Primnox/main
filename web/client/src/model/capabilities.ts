/* Model Capability Layer (CRS §5, CRS/1.0-W §4.7).

   A small static registry, resolved per (provider, model), overridable by
   runtime probes later. Nothing outside this module branches on provider name
   (CRS §13.1.1). Phase 1 only needs the streaming + context-window facts;
   tool-calling emulation lands in Phase 5. */

import { ProviderId } from './types';

export interface Capabilities {
  toolCalling: 'native' | 'emulated' | 'none';
  vision: 'native' | 'none';
  streaming: boolean;
  contextWindow: number;
  maxOutput: number;
}

const DEFAULTS: Record<ProviderId, Capabilities> = {
  openrouter: { toolCalling: 'native', vision: 'native', streaming: true, contextWindow: 128_000, maxOutput: 8_192 },
  groq: { toolCalling: 'native', vision: 'none', streaming: true, contextWindow: 128_000, maxOutput: 8_192 },
  anthropic: { toolCalling: 'native', vision: 'native', streaming: true, contextWindow: 200_000, maxOutput: 8_192 },
  gemini: { toolCalling: 'native', vision: 'native', streaming: true, contextWindow: 1_000_000, maxOutput: 8_192 },
};

// Narrow overrides for models whose window differs sharply from the provider default.
const MODEL_OVERRIDES: Array<{ match: RegExp; patch: Partial<Capabilities> }> = [
  { match: /gpt-4o-mini|gpt-3\.5/i, patch: { contextWindow: 128_000 } },
  { match: /claude-3-haiku/i, patch: { contextWindow: 200_000, maxOutput: 4_096 } },
  { match: /gemini-1\.5-flash/i, patch: { contextWindow: 1_000_000 } },
  { match: /llama-3\.1-8b|gemma2-9b/i, patch: { contextWindow: 8_192, toolCalling: 'emulated' } },
];

export function resolveCapabilities(provider: ProviderId, model: string): Capabilities {
  let caps = { ...DEFAULTS[provider] };
  for (const o of MODEL_OVERRIDES) {
    if (o.match.test(model)) caps = { ...caps, ...o.patch };
  }
  return caps;
}
