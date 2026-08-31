import { Provider, ProviderId } from '../types';
import { makeOpenAICompatProvider } from './openai-compat';
import { anthropicProvider } from './anthropic';
import { geminiProvider } from './gemini';

export const openrouterProvider: Provider = makeOpenAICompatProvider({
  id: 'openrouter',
  defaultBaseUrl: 'https://openrouter.ai/api/v1',
  extraHeaders: () => ({
    // optional attribution headers OpenRouter recommends for browser apps
    'http-referer': typeof location !== 'undefined' ? location.origin : 'https://primnox.web',
    'x-title': 'Primnox Web',
  }),
});

export const groqProvider: Provider = makeOpenAICompatProvider({
  id: 'groq',
  defaultBaseUrl: 'https://api.groq.com/openai/v1',
});

export const providers: Record<ProviderId, Provider> = {
  openrouter: openrouterProvider,
  groq: groqProvider,
  anthropic: anthropicProvider,
  gemini: geminiProvider,
};

export { makeOpenAICompatProvider, anthropicProvider, geminiProvider };
