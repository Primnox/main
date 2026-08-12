import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, screen, fireEvent, waitFor } from '@testing-library/react';
import { Step3AIProvider } from './OnboardingView';

/**
 * Regression guard for the onboarding key-connect step, which used to be
 * hardcoded to Groq regardless of which cloud provider the previous step
 * (Step2Privacy) advertised. This exercises the fix: a provider picker that
 * validates via the backend's /api/provider_models (shared with Settings),
 * not a direct call to the provider's own API.
 */

function jsonResponse(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);
}

beforeEach(() => {
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Step3AIProvider', () => {
  it('defaults to Groq and falls back to it when active_model is unset', () => {
    render(<Step3AIProvider next={() => {}} updateSettings={() => {}} settings={{}} />);
    expect(screen.getByPlaceholderText('gsk_...')).not.toBeNull();
  });

  it('preselects the provider matching an already-set active_model', () => {
    render(<Step3AIProvider next={() => {}} updateSettings={() => {}} settings={{ active_model: 'Anthropic_Claude_3' }} />);
    expect(screen.getByPlaceholderText('sk-ant-...')).not.toBeNull();
  });

  it('switches the key field and clears any entered key when the provider tab changes', () => {
    render(<Step3AIProvider next={() => {}} updateSettings={() => {}} settings={{}} />);

    fireEvent.change(screen.getByPlaceholderText('gsk_...'), { target: { value: 'gsk_something' } });
    fireEvent.click(screen.getByRole('button', { name: 'OpenAI' }));

    expect((screen.getByPlaceholderText('sk-...') as HTMLInputElement).value).toBe('');
  });

  it('validates the key via /api/provider_models, not the provider API directly', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReturnValue(
      jsonResponse({ source: 'live', models: ['gpt-4o'] }),
    );
    const updateSettings = vi.fn();
    render(<Step3AIProvider next={() => {}} updateSettings={updateSettings} settings={{}} />);

    fireEvent.click(screen.getByRole('button', { name: 'OpenAI' }));
    fireEvent.change(screen.getByPlaceholderText('sk-...'), { target: { value: 'sk-real-key' } });
    fireEvent.click(screen.getByRole('button', { name: 'Test Key' }));

    await waitFor(() => expect(updateSettings).toHaveBeenCalled());

    const [url, opts] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(url)).toContain('/api/provider_models');
    expect(JSON.parse((opts as RequestInit).body as string)).toEqual({
      provider: 'openai',
      api_key: 'sk-real-key',
    });
    expect(updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({ openai_api_key: 'sk-real-key', active_model: 'OpenAI_GPT_4o' }),
    );
  });

  it('treats a fallback-source response as an invalid key, not success', async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReturnValue(
      jsonResponse({ source: 'fallback', models: ['gpt-4o'], error: 'HTTP 401' }),
    );
    const updateSettings = vi.fn();
    render(<Step3AIProvider next={() => {}} updateSettings={updateSettings} settings={{}} />);

    fireEvent.change(screen.getByPlaceholderText('gsk_...'), { target: { value: 'gsk_bad' } });
    fireEvent.click(screen.getByRole('button', { name: 'Test Key' }));

    await screen.findByText('Invalid key or connection failed.');
    expect(updateSettings).not.toHaveBeenCalled();
  });
});
