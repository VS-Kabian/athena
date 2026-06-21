"use client";
import { useEffect, useState } from "react";
import { getKeys } from "@/lib/api";
import type { SearchSpec } from "@/lib/types";

const ALL = [
  { id: "ddg", label: "DuckDuckGo", key: false },
  { id: "searxng", label: "SearXNG", key: false },
  { id: "tavily", label: "Tavily", key: true },
  { id: "serper", label: "Serper", key: true },
];

export function SearchPicker({ onChange, disabled }: { onChange: (v: SearchSpec) => void; disabled?: boolean }) {
  const [sel, setSel] = useState<string[]>(["ddg", "searxng"]);
  const [mode, setMode] = useState("broadcast");
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  useEffect(() => {
    getKeys().then((ks) => {
      const saved = new Set(ks.filter((k) => k.set).map((k) => k.provider));
      setSavedKeys(saved);
      // Auto-enable a strong key-based engine (Tavily/Serper) when its key is saved — Google-grade
      // recall surfaces far more authoritative sources than the two free engines alone, which is the
      // single biggest lever for source quality. Users with no key are unaffected (no dead provider).
      setSel((s) => {
        const add = ["tavily", "serper"].filter((p) => saved.has(p) && !s.includes(p));
        return add.length ? [...s, ...add] : s;
      });
    }).catch(() => {});
  }, []);
  useEffect(() => { onChange({ providers: sel, mode, keys: {} }); }, [sel, mode]); // eslint-disable-line
  const toggle = (id: string) => setSel((s) => {
    if (!s.includes(id)) return [...s, id];
    return s.length === 1 ? s : s.filter((x) => x !== id);   // never deselect the last provider
  });
  const modes = [["broadcast", "All at once"], ["single", "Single"], ["priority", "Priority"]];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {ALL.map((p) => (
          <label key={p.id} className={`pill ${sel.includes(p.id) ? "on" : ""}`}>
            <input type="checkbox" aria-label={p.label} checked={sel.includes(p.id)} disabled={disabled} onChange={() => toggle(p.id)} />
            {p.label}{p.key && savedKeys.has(p.id) ? " 🔑" : ""}
          </label>
        ))}
      </div>
      <div className="seg" role="group" aria-label="search mode">
        {modes.map(([v, l]) => (
          <button key={v} type="button" className={mode === v ? "on" : ""} disabled={disabled} onClick={() => setMode(v)}>{l}</button>
        ))}
      </div>
    </div>
  );
}
