"use client";

export function QualityMeter({ score, risk }: { score: number; risk: number }) {
  const hue = Math.round((score / 100) * 120); // red→green
  return (
    <div className="flex items-center gap-4" aria-label="quality meter">
      <div
        role="meter"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="research quality score"
        className="relative flex items-center justify-center"
        style={{
          width: 64, height: 64, borderRadius: "50%",
          background: `conic-gradient(hsl(${hue} 70% 55%) ${score * 3.6}deg, rgba(255,255,255,0.08) 0deg)`,
        }}
      >
        <span className="absolute inset-[6px] rounded-full flex items-center justify-center text-sm font-semibold"
              style={{ background: "var(--bg)" }}>
          {score}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-xs" style={{ color: "var(--muted)" }}>Quality score</span>
        <span className="text-xs" style={{ color: "var(--muted)" }}>
          Hallucination risk:{" "}
          <span style={{ color: risk > 0.1 ? "#FB7185" : "#34D399" }}
                aria-label={`hallucination risk ${risk > 0.1 ? "elevated" : "low"}`}>
            <span aria-hidden="true">{risk > 0.1 ? "⚠ " : "✓ "}</span>
            <span>{Math.round(risk * 100)}%</span>
          </span>
        </span>
      </div>
    </div>
  );
}
