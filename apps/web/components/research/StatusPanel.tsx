"use client";
import { Timer } from "./Timer";
import { QualityMeter } from "./QualityMeter";

type Props = {
  status: string; round: number; roundsTotal: number;
  discovered: number; validated: number; model: string;
  providers: string[]; running: boolean;
  quality?: { score: number; risk: number } | null;
};

export function StatusPanel({ status, round, roundsTotal, discovered, validated, model, providers, running, quality }: Props) {
  const rows = [
    { k: "Status", v: status },
    { k: "Round", v: `${round} / ${roundsTotal}` },
    { k: "Sources discovered", v: String(discovered) },
    { k: "Validated sources", v: String(validated) },
    { k: "Active model", v: model || "—" },
    { k: "Search providers", v: providers.length ? providers.join(", ") : "—" },
  ];
  return (
    <div className="card" aria-live="polite" aria-label="status panel" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div className="flex items-center justify-between">
        <span className="card-label" style={{ margin: 0 }}>Elapsed</span>
        <span className="stat-value" style={{ color: running ? "var(--accent)" : "var(--text)" }}><Timer running={running} /></span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {rows.map((r) => (
          <div className="stat-row" key={r.k}>
            <span className="k">{r.k}</span>
            <span style={{ fontSize: 15, fontWeight: 600 }}>{r.v}</span>
          </div>
        ))}
      </div>
      {quality && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
          <QualityMeter score={quality.score} risk={quality.risk} />
        </div>
      )}
    </div>
  );
}
