"use client";
import { useEffect, useState } from "react";
import { getKeys, putKey, deleteKey, testKey, type SavedKey } from "@/lib/api";

const PROVIDERS = [
  { id: "groq", label: "Groq", hint: "console.groq.com/keys" },
  { id: "gemini", label: "Google Gemini", hint: "aistudio.google.com/apikey" },
  { id: "deepseek", label: "DeepSeek", hint: "platform.deepseek.com" },
  { id: "tavily", label: "Tavily (search)", hint: "app.tavily.com" },
  { id: "serper", label: "Serper (search)", hint: "serper.dev" },
];

type Msg = { kind: "ok" | "err"; text: string };

export function KeyVault() {
  const [saved, setSaved] = useState<Record<string, SavedKey>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [msg, setMsg] = useState<Record<string, Msg | undefined>>({});
  const [apiError, setApiError] = useState(false);

  async function refresh() {
    try {
      const list = await getKeys();
      setSaved(Object.fromEntries(list.map((k) => [k.provider, k])));
      setApiError(false);
    } catch {
      setApiError(true);
    }
  }
  useEffect(() => { refresh(); }, []);

  async function save(p: string) {
    if (!draft[p]) return;
    setBusy(p);
    setMsg((m) => ({ ...m, [p]: undefined }));
    try {
      const res = await putKey(p, draft[p]);
      if (!res.ok) {
        setMsg((m) => ({ ...m, [p]: { kind: "err", text: `Couldn't save (HTTP ${res.status}). Restart the API server so it serves /api/keys.` } }));
      } else {
        setDraft((d) => ({ ...d, [p]: "" }));
        await refresh();
        setMsg((m) => ({ ...m, [p]: { kind: "ok", text: "Saved securely." } }));
      }
    } catch {
      setMsg((m) => ({ ...m, [p]: { kind: "err", text: "API not reachable — is the backend running on :7000?" } }));
    } finally {
      setBusy(null);
    }
  }

  async function test(p: string) {
    setTesting(p);
    setMsg((m) => ({ ...m, [p]: undefined }));
    try {
      const res = await testKey(p);
      setMsg((m) => ({ ...m, [p]: { kind: res.ok ? "ok" : "err", text: res.message } }));
    } catch {
      setMsg((m) => ({ ...m, [p]: { kind: "err", text: "API not reachable." } }));
    } finally {
      setTesting(null);
    }
  }

  async function remove(p: string) {
    setBusy(p);
    setMsg((m) => ({ ...m, [p]: undefined }));
    try {
      const res = await deleteKey(p);
      if (!res.ok) {
        setMsg((m) => ({ ...m, [p]: { kind: "err", text: `Couldn't remove (HTTP ${res.status}).` } }));
      } else {
        await refresh();
      }
    } catch {
      setMsg((m) => ({ ...m, [p]: { kind: "err", text: "API not reachable." } }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-3" style={{ maxWidth: 720 }}>
      {apiError && (
        <div className="card" role="alert" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          ⚠ Can't reach the API key store. Start or restart the backend so it serves <code>/api/keys</code>:
          <code style={{ display: "block", marginTop: 8, color: "var(--muted)" }}>
            cd services/api &amp;&amp; .venv/Scripts/python -m uvicorn athena.api.app:app --port 7000
          </code>
        </div>
      )}
      {PROVIDERS.map((p) => {
        const s = saved[p.id];
        const m = msg[p.id];
        return (
          <div key={p.id} className="card" aria-label={`key ${p.id}`}>
            <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
              <div className="flex flex-col">
                <span style={{ fontWeight: 600 }}>{p.label}</span>
                <span style={{ color: "var(--faint)", fontSize: 12.5 }}>{p.hint}</span>
              </div>
              {s?.set
                ? <span className="tag ok">saved · {s.masked}</span>
                : <span className="tag">not set</span>}
            </div>
            <div className="flex gap-2">
              <input className="field" type="password" aria-label={`${p.id} input`}
                     placeholder={s?.set ? "Replace key…" : "Paste API key…"}
                     value={draft[p.id] ?? ""} onChange={(e) => setDraft((d) => ({ ...d, [p.id]: e.target.value }))} />
              <button className="btn-primary btn-sm" disabled={busy === p.id || !draft[p.id]} onClick={() => save(p.id)}>
                {busy === p.id ? "…" : "Save"}
              </button>
              {s?.set && (
                <button className="btn-ghost btn-sm" disabled={testing === p.id || busy === p.id}
                        onClick={() => test(p.id)}>{testing === p.id ? "…" : "Test"}</button>
              )}
              {s?.set && (
                <button className="btn-ghost btn-sm" disabled={busy === p.id} onClick={() => remove(p.id)}>Remove</button>
              )}
            </div>
            {m && (
              <div style={{ marginTop: 10, fontSize: 13, color: m.kind === "ok" ? "var(--good)" : "var(--bad)" }}>
                {m.kind === "ok" ? "✓ " : "⚠ "}{m.text}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
