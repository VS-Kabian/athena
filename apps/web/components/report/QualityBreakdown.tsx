"use client";
import type { QualityBreakdown as QB } from "@/lib/types";

const ROWS: { key: keyof QB; label: string; max: number }[] = [
  { key: "coverage", label: "Coverage", max: 18 },
  { key: "validation", label: "Validation", max: 22 },
  { key: "grounding", label: "Grounding", max: 30 },
  { key: "relevance", label: "Relevance", max: 15 },
  { key: "depth", label: "Depth", max: 15 },
];

export function QualityBreakdown({ breakdown }: { breakdown: QB }) {
  return (
    <div className="card" aria-label="quality breakdown" style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 520 }}>
      <div className="card-label" style={{ margin: 0 }}>Quality breakdown</div>
      {ROWS.map((r) => {
        const v = Number(breakdown[r.key] ?? 0);
        const pct = Math.min(100, Math.round((v / r.max) * 100));
        return (
          <div key={r.key} style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ width: 90, fontSize: 13, color: "var(--muted)" }}>{r.label}</span>
            <div style={{ flex: 1, height: 8, background: "var(--surface-2)", borderRadius: 999, overflow: "hidden" }}>
              <div style={{ width: `${pct}%`, height: "100%", background: "linear-gradient(90deg,var(--accent),var(--accent-2))" }} />
            </div>
            <span className="mono" style={{ width: 44, textAlign: "right", fontSize: 12.5 }}>{v}/{r.max}</span>
          </div>
        );
      })}
      {typeof breakdown.hallucination_risk === "number" && (
        <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
          Hallucination risk:{" "}
          <span style={{ color: breakdown.hallucination_risk > 0.1 ? "var(--bad)" : "var(--good)" }}>
            {Math.round(breakdown.hallucination_risk * 100)}%
          </span>
        </div>
      )}
    </div>
  );
}
