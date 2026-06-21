"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getProviders, getModels, getKeys } from "@/lib/api";
import type { Provider, LLMSpec } from "@/lib/types";

export function ModelPicker({ onChange, disabled }: { onChange: (v: LLMSpec | null) => void; disabled?: boolean }) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [hasKey, setHasKey] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProviders().then(setProviders).catch(() => setError("Couldn't load providers — is the API running?"));
  }, []);
  useEffect(() => {
    if (!provider) return;
    setError(null);
    // latest-wins guard: if the user switches provider A->B while getModels(A) is still in flight,
    // A's slower response must not apply over B's. The cleanup flips `stale` so the prior request
    // bails in its `.then`, leaving the selected provider and rendered models consistent.
    let stale = false;
    getModels(provider)
      .then((m) => { if (stale) return; setModels(m); setModel(m[0] ?? ""); })
      .catch(() => { if (stale) return; setModels([]); setModel(""); setError("Couldn't load models for this provider."); });
    getKeys().then((ks) => { if (stale) return; setHasKey(ks.some((k) => k.provider === provider && k.set)); }).catch(() => { if (!stale) setHasKey(false); });
    return () => { stale = true; };
  }, [provider]);
  // clear the parent's selection when there's no valid (provider, model) so a stale model from a
  // previously-chosen provider can't be submitted after switching to one whose models failed to load
  useEffect(() => { onChange(provider && model ? { provider, model } : null); }, [provider, model]); // eslint-disable-line

  const needsKey = providers.find((p) => p.id === provider)?.needs_key;
  return (
    <div className="flex flex-col gap-3">
      <select className="field" aria-label="provider" value={provider} disabled={disabled}
              onChange={(e) => { setProvider(e.target.value); setModel(""); }}>
        <option value="">Select provider…</option>
        {providers.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
      </select>
      {models.length > 0 && (
        <select className="field" aria-label="model" value={model} disabled={disabled} onChange={(e) => setModel(e.target.value)}>
          {models.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      )}
      {provider && needsKey && (
        hasKey
          ? <span className="tag ok">🔑 key saved</span>
          : <Link href="/settings" className="tag" style={{ textDecoration: "none" }}>No key — add in API Keys →</Link>
      )}
      {error && <span role="alert" style={{ color: "var(--bad)", fontSize: 12 }}>{error}</span>}
    </div>
  );
}
