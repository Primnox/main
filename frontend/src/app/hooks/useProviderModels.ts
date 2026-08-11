/**
 * Shared provider/model-list plumbing — originally built inline inside
 * SettingsView.tsx's Intelligence tab, now used by three surfaces (Settings,
 * Knowledge Nexus's Model Library, and the in-chat model switcher) so none of
 * them re-implement the same detection/caching logic.
 *
 * What's shared here: the built-in provider list, the last-resort fallback
 * models, and the stateful "detect + cache" hook. What's NOT shared: each
 * consumer still writes its own tiny modelForProvider/setModelForProvider
 * closures over its own named model props — those are 3-4 lines each and
 * differ (chat models vs. TTS models, which fields exist on a custom
 * provider profile), so forcing them through one generic API would be more
 * abstraction than the actual duplication warrants.
 */
import { useState } from 'react';
import { postJson } from '../components/settings/api';

export type CustomProvider = {
  id: string; name: string; api_type: 'openai' | 'anthropic'; base_url: string; api_key: string; model: string;
};

export const BUILTIN_PROVIDERS = [
  { key: 'groq',      label: 'Groq',      activeModel: 'Groq_Llama_3' },
  { key: 'openai',    label: 'OpenAI',    activeModel: 'OpenAI_GPT_4o' },
  { key: 'anthropic', label: 'Anthropic', activeModel: 'Anthropic_Claude_3' },
  { key: 'gemini',    label: 'Gemini',    activeModel: 'Gemini_Flash' },
] as const;

export type BuiltinProviderKey = typeof BUILTIN_PROVIDERS[number]['key'];

/** Last-resort model per built-in provider for when even our own backend is
 *  unreachable (postJson returns null — network hiccup, backend not up yet).
 *  The backend's /api/provider_models already has its own curated fallback
 *  for when the *provider's* API fails; this is the layer below that. Only
 *  meaningful for capability="chat" — there's no safe default TTS model to
 *  guess at. */
export const FRONTEND_LAST_RESORT: Record<string, string[]> = {
  groq: ['llama-3.3-70b-versatile'],
  openai: ['gpt-4o'],
  anthropic: ['claude-3-5-sonnet-20241022'],
  gemini: ['gemini-2.0-flash'],
};

export type ModelsResult = { models: string[]; error?: string; source?: 'live' | 'fallback' };

/** Resolves which provider is "currently selected" from activeModel/
 *  activeCustomProviderId — used by surfaces with a single current-provider
 *  concept (Settings' architecture picker, the in-chat switcher). Knowledge
 *  Nexus's Model Library shows every provider at once and doesn't need this. */
export const selectedProviderKeyFor = (activeModel: string, activeCustomProviderId: string): string =>
  activeModel === 'Custom'
    ? activeCustomProviderId
    : (BUILTIN_PROVIDERS.find(p => p.activeModel === activeModel)?.key ?? 'groq');

export const selectProviderAction = (
  key: string,
  setActiveModel: (v: string) => void,
  setActiveCustomProviderId: (v: string) => void,
) => {
  const builtin = BUILTIN_PROVIDERS.find(p => p.key === key);
  if (builtin) { setActiveModel(builtin.activeModel); return; }
  setActiveModel('Custom');
  setActiveCustomProviderId(key);
};

/** Core model-list cache + detection. Each caller gets its own cache instance
 *  and decides when to call detectModelsFor — a "one selected provider"
 *  surface fetches on selection change, a "show everything" surface fetches
 *  for every provider up front. */
export function useProviderModels(opts: {
  apiKeys: Record<BuiltinProviderKey, string>;
  customProviders: CustomProvider[];
  capability?: 'chat' | 'tts';
}) {
  const { apiKeys, customProviders, capability = 'chat' } = opts;
  const [providerModelsCache, setProviderModelsCache] = useState<Record<string, ModelsResult>>({});
  const [detectingProvider, setDetectingProvider] = useState<string | null>(null);

  const detectModelsFor = async (key: string) => {
    setDetectingProvider(key);
    const isBuiltin = BUILTIN_PROVIDERS.some(p => p.key === key);
    let result: ModelsResult | null;
    if (isBuiltin) {
      result = await postJson<ModelsResult>('/api/provider_models', {
        provider: key, api_key: apiKeys[key as BuiltinProviderKey], capability,
      });
    } else if (capability === 'chat') {
      const profile = customProviders.find(p => p.id === key);
      result = await postJson<ModelsResult>('/api/custom_provider/models', {
        base_url: profile?.base_url, api_type: profile?.api_type, api_key: profile?.api_key, profile_id: key,
      });
    } else {
      // Custom endpoint profiles don't carry a separate TTS model field —
      // nothing to detect for them under capability="tts".
      result = { models: [], source: 'live' };
    }
    if (!result) {
      result = capability === 'chat'
        ? { models: FRONTEND_LAST_RESORT[key] || [], error: 'Could not reach the backend.', source: 'fallback' }
        : { models: [], error: 'Could not reach the backend.', source: 'fallback' };
    }
    setProviderModelsCache(prev => ({ ...prev, [key]: result! }));
    setDetectingProvider(null);
  };

  /** Drops a stale cache entry — call after editing/deleting a custom
   *  endpoint so its old model list doesn't linger until the next detect. */
  const clearCache = (key: string) => {
    setProviderModelsCache(prev => {
      const { [key]: _drop, ...rest } = prev;
      return rest;
    });
  };

  return { providerModelsCache, detectingProvider, detectModelsFor, clearCache };
}
