"use client";

// Per-claim verdict ledger (P1-7) — the auditable trail behind the trust score. The backend already
// persists every cited claim's entailment verdict (Supported / Refuted / Not-Enough-Info), confidence,
// and cross-source conflict flag; this surfaces them so a reader can audit the report claim by claim.

import type { Claim } from "@/lib/types";

const VERDICT: Record<string, { label: string; color: string }> = {
  supported: { label: "Supported", color: "#34D399" },
  refuted: { label: "Refuted", color: "#FB7185" },
  nei: { label: "Not enough info", color: "#FBBF24" },
  unverified: { label: "Unverified", color: "#FBBF24" },
};

export function ClaimsTable({ claims }: { claims: Claim[] }) {
  if (!claims.length) return null;
  return (
    <div className="card flex flex-col gap-3" aria-label="claim verdicts">
      <h3 className="font-semibold">Claim verdicts ({claims.length})</h3>
      <ul className="flex flex-col gap-2">
        {claims.map((c, i) => {
          const v = VERDICT[c.verdict] ?? { label: c.verdict || "Unverified", color: "var(--muted)" };
          return (
            <li key={i} className="flex gap-2 items-start text-sm">
              <span style={{
                color: v.color, border: `1px solid ${v.color}`, borderRadius: 6,
                padding: "1px 7px", fontSize: 11, fontWeight: 700, whiteSpace: "nowrap", marginTop: 1,
              }}>{v.label}</span>
              {c.conflict && (
                <span style={{
                  color: "#C084FC", border: "1px solid #C084FC", borderRadius: 6,
                  padding: "1px 7px", fontSize: 11, fontWeight: 700, whiteSpace: "nowrap", marginTop: 1,
                }}>Conflict</span>
              )}
              <span style={{ color: "var(--muted)", wordBreak: "break-word" }}>{c.text}</span>
              {c.confidence != null && (
                <span className="text-xs" style={{ color: "var(--faint)", marginLeft: "auto", whiteSpace: "nowrap" }}>
                  {Math.round(c.confidence * 100)}%
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
