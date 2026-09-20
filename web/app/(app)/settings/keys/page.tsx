'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { Eye, EyeOff, Info, KeyRound, Plus, Trash2 } from 'lucide-react';
import { PROVIDERS, PROVIDER_SELECT_ORDER } from '@/lib/llm/providers';
import { buildByokHeaders } from '@/lib/llm/byok';
import { useKeysStore, type StoredKey } from '@/lib/store/keys';
import { mask } from '@/lib/utils/mask';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Dialog } from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { FormField } from '@/components/ui/form-field';
import { Input } from '@/components/ui/input';
import { Pill } from '@/components/ui/pill';
import { Select } from '@/components/ui/select';
import { usePageInfo } from '@/components/shell/shell-context';

type TestResult = { ok: boolean; message: string };

function KeyRow({ storedKey, isDefault }: { storedKey: StoredKey; isDefault: boolean }) {
  const setDefault = useKeysStore((s) => s.setDefault);
  const removeKey = useKeysStore((s) => s.removeKey);
  const tier = useKeysStore((s) => s.tier);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const meta = PROVIDERS[storedKey.provider];

  const testKey = async () => {
    setTesting(true);
    try {
      const response = await fetch('/api/generate/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...buildByokHeaders(storedKey, tier) },
        body: '{}',
      });
      if (response.ok) {
        const latency = response.headers.get('x-qag-latency-ms');
        const model = response.headers.get('x-qag-model') ?? 'model';
        const message = latency ? `OK · ${latency} ms · ${model}` : `OK · ${model}`;
        setTestResult({ ok: true, message });
        toast.success(message);
      } else {
        const data: unknown = await response.json().catch(() => null);
        const message =
          data && typeof data === 'object' && 'message' in data && typeof data.message === 'string'
            ? data.message
            : 'The key test failed.';
        setTestResult({ ok: false, message: 'failed' });
        toast.error(message);
      }
    } catch {
      setTestResult({ ok: false, message: 'failed' });
      toast.error('The key test failed. Check the key and try again.');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-[var(--qg-radius)] border border-border bg-card px-3 py-2.5">
      <input
        type="radio"
        name="default-key"
        checked={isDefault}
        onChange={() => setDefault(storedKey.id)}
        aria-label={`Set ${meta.displayName} as default`}
        className="h-4 w-4 accent-[var(--qg-accent)]"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[14px] font-medium">{meta.displayName}</span>
          {isDefault ? <Pill tone="accent">Default</Pill> : null}
          {testResult ? (
            <Pill tone={testResult.ok ? 'ok' : 'bad'}>{testResult.message}</Pill>
          ) : null}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-muted">
          <span>{storedKey.label}</span>
          <span className="font-mono">{mask(storedKey.apiKey)}</span>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <Button variant="secondary" onClick={testKey} loading={testing}>
          Test
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Delete ${meta.displayName} key`}
          onClick={() => setConfirmOpen(true)}
        >
          <Trash2 className="h-4 w-4 text-bad-fg" aria-hidden />
        </Button>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen} title="Delete key">
        <p className="text-[14px] text-text-2">
          Remove the {meta.displayName} key from this browser? You can add it again any time.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              removeKey(storedKey.id);
              setConfirmOpen(false);
              toast.success('Key deleted');
            }}
          >
            Delete
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

export default function KeysSettingsPage() {
  usePageInfo({ workspace: 'Settings', tab: 'Keys' });
  const keys = useKeysStore((s) => s.keys);
  const defaultKeyId = useKeysStore((s) => s.defaultKeyId);
  const addKey = useKeysStore((s) => s.addKey);

  const [provider, setProvider] = useState<string>('gemini');
  const [label, setLabel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const providerId = (PROVIDER_SELECT_ORDER as readonly string[]).includes(provider)
    ? (provider as (typeof PROVIDER_SELECT_ORDER)[number])
    : 'gemini';
  const meta = PROVIDERS[providerId];

  const save = () => {
    if (!apiKey.trim()) {
      setFormError('Enter an API key.');
      return;
    }
    if (meta.needsBaseUrl && !/^https?:\/\//.test(baseUrl.trim())) {
      setFormError('Base URL must start with http(s)://');
      return;
    }
    setFormError(null);
    addKey({
      provider: providerId,
      label: label.trim() || meta.displayName,
      apiKey: apiKey.trim(),
      ...(meta.needsBaseUrl ? { baseUrl: baseUrl.trim() } : {}),
      ...(model.trim() ? { model: model.trim() } : {}),
    });
    setLabel('');
    setApiKey('');
    setBaseUrl('');
    setModel('');
    toast.success('Key saved');
  };

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <h1 className="font-display text-[22px] font-semibold">Settings</h1>

      <div className="flex items-start gap-2.5 rounded-[var(--qg-radius-card)] border border-border bg-card p-4">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-info-fg" aria-hidden />
        <p className="text-[13px] leading-relaxed text-text-2">
          Keys live only in this browser&apos;s storage. Each request sends your key to your chosen
          provider through this app&apos;s server, which never stores or logs it. Delete a key any
          time.
        </p>
      </div>

      <Card>
        <CardHeader title="Your keys" />
        {keys.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            headline="No keys yet"
            description="Add an API key below to start generating."
            className="border-0 bg-transparent py-8"
          />
        ) : (
          <div className="flex flex-col gap-2">
            {keys.map((k) => (
              <KeyRow key={k.id} storedKey={k} isDefault={k.id === (defaultKeyId ?? keys[0]?.id)} />
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Add key" />
        <div className="flex flex-col gap-3">
          <FormField label="Provider">
            <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDER_SELECT_ORDER.map((id) => (
                <option key={id} value={id}>
                  {PROVIDERS[id].displayName}
                </option>
              ))}
            </Select>
          </FormField>
          {meta.keyHelpUrl ? (
            <p className="-mt-1 text-[12px] text-muted">
              <a
                href={meta.keyHelpUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent underline-offset-2 hover:underline"
              >
                Get a free key
              </a>
            </p>
          ) : null}
          <FormField label="Label" helper="Optional — defaults to the provider name.">
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={meta.displayName}
              maxLength={60}
            />
          </FormField>
          <FormField label="API key" htmlFor="api-key-input">
            <div className="relative">
              <Input
                id="api-key-input"
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste your key"
                autoComplete="off"
                className="pr-9"
              />
              <button
                type="button"
                onClick={() => setShowKey((v) => !v)}
                aria-label={showKey ? 'Hide key' : 'Show key'}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-[var(--qg-radius)] p-1.5 text-muted hover:bg-card-2 hover:text-text"
              >
                {showKey ? (
                  <EyeOff className="h-4 w-4" aria-hidden />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden />
                )}
              </button>
            </div>
          </FormField>
          {meta.needsBaseUrl ? (
            <FormField label="Base URL" helper="Required for an OpenAI-compatible provider.">
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:11434/v1"
              />
            </FormField>
          ) : null}
          <FormField
            label="Model override"
            helper="Optional — overrides the default model for both tiers."
          >
            <Input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={meta.defaultModels.fast}
            />
          </FormField>
          {formError ? (
            <p className="text-[12px] text-bad-fg" role="alert">
              {formError}
            </p>
          ) : null}
          <div>
            <Button variant="primary" onClick={save}>
              <Plus className="h-4 w-4" aria-hidden />
              Save key
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
