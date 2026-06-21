"use client";
import { useState } from "react";
import type { Citation } from "@/lib/types";
import { safeHref } from "@/lib/safeHref";

export function CitationChip({ n, citation }: { n: number; citation?: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: "relative", display: "inline-block" }}
      onFocus={() => setOpen(true)}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false); }}>
      <button
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        aria-label={`citation ${n}`}
        style={{
          cursor: "pointer", border: "none", background: "var(--accent-soft)", color: "var(--accent)",
          borderRadius: 5, padding: "0 5px", fontSize: 12, fontWeight: 700, margin: "0 1px",
          verticalAlign: "super", lineHeight: 1.4,
        }}
      >[{n}]</button>
      {open && citation && (
        <span role="tooltip" style={{
          position: "absolute", left: 0, bottom: "140%", zIndex: 20, width: 340,
          background: "var(--bg-2)", border: "1px solid var(--border-strong)", borderRadius: 12,
          padding: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.5)", textAlign: "left", whiteSpace: "normal",
        }}>
          <a href={safeHref(citation.url)} target="_blank" rel="noreferrer"
             style={{ color: "var(--accent)", fontSize: 12.5, fontWeight: 600, textDecoration: "none", display: "block", marginBottom: 6 }}>
            [{n}] {citation.title?.slice(0, 70) || citation.url}
          </a>
          <span style={{ color: "var(--muted)", fontSize: 12, lineHeight: 1.5 }}>
            “{(citation.excerpt || "").slice(0, 260)}{(citation.excerpt || "").length > 260 ? "…" : ""}”
          </span>
        </span>
      )}
    </span>
  );
}
