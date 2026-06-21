"use client";

// Live coverage ledger (#1): shows how well each sub-question is covered by validated, on-topic
// evidence as the agent reads and re-queries — the read→discover→re-query loop made visible. Also
// surfaces the entailment + link-health checks once they run.

import type { Coverage, EntailSummary, UrlHealth } from "@/lib/types";

function bar(score: number) {
  const pct = Math.round(Math.max(0, Math.min(score, 1)) * 100);
  const color = score >= 0.5 ? "#34D399" : score >= 0.25 ? "#FBBF24" : "#FB7185";
  return { pct, color };
}

export function CoveragePanel({ coverage, entail, urlHealth }:
  { coverage: Coverage; entail?: EntailSummary | null; urlHealth?: UrlHealth | null }) {
  const overall = Math.round((coverage.overall ?? 0) * 100);
  return (
    <div className="card flex flex-col gap-3" aria-label="coverage ledger">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">📊 Coverage ledger</h3>
        <span className="tag">{overall}% covered</span>
      </div>
      <ul className="flex flex-col gap-2">
        {coverage.cells.map((c, i) => {
          const { pct, color } = bar(c.score);
          return (
            <li key={i} className="flex flex-col gap-1">
              <div className="flex items-center justify-between" style={{ fontSize: 13 }}>
                <span style={{ color: "var(--muted)", wordBreak: "break-word", paddingRight: 8 }}>{c.question}</span>
                <span style={{ color: "var(--faint)", fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "nowrap" }}>
                  {c.validated}✓ · {c.relevant} rel
                </span>
              </div>
              <div style={{ height: 6, borderRadius: 4, background: "var(--border)", overflow: "hidden" }}>
                <div style={{ width: `${pct}%`, height: "100%", background: color, transition: "width .4s ease" }} />
              </div>
            </li>
          );
        })}
      </ul>

      {coverage.entities.length > 0 && (
        <div className="flex flex-wrap gap-2" style={{ marginTop: 2 }}>
          {coverage.entities.map((e, i) => (
            <span key={i} className="tag" title={`${e.hits} source(s)`}
              style={{ opacity: e.covered ? 1 : 0.5, borderColor: e.covered ? "#34D399" : "var(--border)" }}>
              {e.covered ? "✓ " : "○ "}{e.entity}
            </span>
          ))}
        </div>
      )}

      {(entail || urlHealth) && (
        <div className="flex flex-wrap gap-4" style={{ borderTop: "1px solid var(--border)", paddingTop: 10, fontSize: 12.5, color: "var(--muted)" }}>
          {entail && entail.engine === "entailment" && (
            <span>Entailment: <strong style={{ color: "#34D399" }}>{entail.supported}</strong> supported
              {entail.refuted > 0 ? <>, <strong style={{ color: "#FB7185" }}>{entail.refuted}</strong> refuted</> : null}
              {entail.conflicts > 0 ? <>, <strong style={{ color: "#C084FC" }}>{entail.conflicts}</strong> conflicts</> : null}
            </span>
          )}
          {urlHealth && urlHealth.total > 0 && (
            <span>Links: <strong style={{ color: urlHealth.dead > 0 ? "#FB7185" : "#34D399" }}>{urlHealth.live}/{urlHealth.total}</strong> live</span>
          )}
        </div>
      )}
    </div>
  );
}
