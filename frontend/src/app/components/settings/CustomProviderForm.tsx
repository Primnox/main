/**
 * Add/edit form for a saved custom-endpoint profile — originally inline JSX
 * inside SettingsView.tsx's Intelligence tab, extracted so Knowledge Nexus's
 * Model Library can render the identical add/edit UI instead of duplicating
 * it. Fully self-contained: owns its own draft state, does its own
 * detect/save network calls, and only reports back the finished result.
 */
import { useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { postJson, putJson } from './api';
import { Row, Field, SecretField, Select, Button, Status } from './primitives';
import type { CustomProvider, ModelsResult } from '../../hooks/useProviderModels';

/** Mirrors brain.py's _is_local_url — same local-vs-cloud classification the
 *  backend uses to decide whether Privacy Mirror applies to this endpoint. */
const isCustomUrlLocal = (url: string): boolean =>
  /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/?$/.test((url || '').trim());

export const CustomProviderForm = ({ editing, onSave, onCancel }: {
  editing: CustomProvider | null;
  onSave: (profile: CustomProvider, isNew: boolean) => void;
  onCancel: () => void;
}) => {
  const [name, setName] = useState(editing?.name || '');
  const [apiType, setApiType] = useState<'openai' | 'anthropic'>(editing?.api_type || 'openai');
  const [baseUrl, setBaseUrl] = useState(editing?.base_url || '');
  const [apiKey, setApiKey] = useState(editing?.api_key || '');
  const [model, setModel] = useState(editing?.model || '');
  const [detected, setDetected] = useState<string[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detectModels = async () => {
    setDetecting(true);
    setError(null);
    const d = await postJson<ModelsResult>('/api/custom_provider/models', {
      base_url: baseUrl, api_type: apiType, api_key: apiKey, profile_id: editing?.id,
    });
    if (d?.models?.length) setDetected(d.models);
    else { setDetected([]); setError(d?.error || 'No models found at that URL.'); }
    setDetecting(false);
  };

  const save = async () => {
    if (!name.trim() || !baseUrl.trim()) return;
    const payload = { name: name.trim(), api_type: apiType, base_url: baseUrl.trim(), api_key: apiKey, model };
    const saved = editing
      ? await putJson<CustomProvider>(`/api/custom_providers/${editing.id}`, payload)
      : await postJson<CustomProvider>('/api/custom_providers', payload);
    if (saved) onSave(saved, !editing);
  };

  return (
    <Row label={editing ? 'Edit custom endpoint' : 'New custom endpoint'} stack>
      <div className="p-5 border border-on-surface/10 bg-[var(--hover)] space-y-4">
        <Field value={name} onChange={setName} placeholder="Name — e.g. My vLLM box" />
        <div className="flex gap-2">
          <Button variant={apiType === 'openai' ? 'solid' : 'ghost'} onClick={() => setApiType('openai')}>OpenAI-compatible</Button>
          <Button variant={apiType === 'anthropic' ? 'solid' : 'ghost'} onClick={() => setApiType('anthropic')}>Anthropic-compatible</Button>
        </div>
        <Field value={baseUrl} onChange={setBaseUrl} mono placeholder="http://localhost:8000 or https://api.example.com" />
        {baseUrl.trim() && (
          <Status tone={isCustomUrlLocal(baseUrl) ? 'good' : 'warn'}>
            {isCustomUrlLocal(baseUrl) ? 'Local — nothing leaves this machine' : 'Cloud — follows the Privacy Mirror toggle'}
          </Status>
        )}
        <SecretField value={apiKey} onChange={setApiKey} placeholder="API key (leave blank if none needed)" />
        <div className="flex gap-2">
          <Field value={model} onChange={setModel} mono placeholder="model-name" />
          <Button onClick={detectModels} disabled={detecting || !baseUrl}>
            <RefreshCw size={11} className={`inline mr-2 ${detecting ? 'animate-spin' : ''}`} />
            {detecting ? 'Detecting' : 'Detect models'}
          </Button>
        </div>
        {error && <p className="font-mono text-[10px] text-error">{error}</p>}
        {detected.length > 0 && (
          <Select value={model} onChange={setModel} options={detected.map(m => ({ value: m, label: m }))} />
        )}
        <div className="flex gap-3 pt-1">
          <Button variant="solid" onClick={save} disabled={!name.trim() || !baseUrl.trim()}>Save</Button>
          <Button onClick={onCancel}><X size={11} className="inline mr-2" />Cancel</Button>
        </div>
      </div>
    </Row>
  );
};
