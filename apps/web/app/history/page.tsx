"use client";
import { useEffect, useState } from "react";

type Item = { id: string; topic: string; ts: number };

export default function HistoryPage() {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => {
    try { setItems(JSON.parse(localStorage.getItem("athena:history") || "[]")); } catch { setItems([]); }
  }, []);
  return (
    <div className="flex flex-col gap-7">
      <header>
        <h1 className="page-title">History</h1>
        <p className="page-sub">Your recent research runs (stored locally).</p>
      </header>
      {items.length === 0
        ? <div className="card" style={{ color: "var(--muted)" }}>No runs yet. Start one from New Research.</div>
        : <div className="flex flex-col gap-2" style={{ maxWidth: 720 }}>
            {items.map((it) => (
              <div key={it.id} className="card flex items-center justify-between">
                <span style={{ fontWeight: 600 }}>{it.topic || "Untitled"}</span>
                <span className="tag">{new Date(it.ts).toLocaleString()}</span>
              </div>
            ))}
          </div>}
    </div>
  );
}
