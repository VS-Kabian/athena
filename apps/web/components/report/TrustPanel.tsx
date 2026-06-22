"use client";

// The Trust Ledger — ATHENA's signature differentiator. Surfaces per-claim verification as a
// color-coded panel: entailment verdicts (Supported / Refuted / Not-Enough-Info), cross-source
// CONFLICTS, second-model corrections, and dead-link detection. The structured `trust` summary comes
// from the report row; `flagged` carries the human-readable per-claim warnings.

import type { Trust } from "@/lib/types";

type Verdict =
  | "corrected" | "weak" | "single-source" | "unsupported"
  | "refuted" | "nei" | "conflict" | "link-dead" | "contradicted";

const BADGES: Record<Verdict, { label: string; color: string }> = {
  corrected: { label: "Corrected", color: "#34D399" },
  refuted: { label: "Refuted", color: "#FB7185" },
  contradicted: { label: "Contradicted", color: "#FB7185" },
  conflict: { label: "Conflict", color: "#C084FC" },
  nei: { label: "Not enough info", color: "#FBBF24" },
  weak: { label: "Weak support", color: "#FBBF24" },
  "single-source": { label: "Single source", color: "#60A5FA" },
  "link-dead": { label: "Dead link", color: "#FB7185" },
  unsupported: { label: "Unsupported", color: "#FB7185" },
};

export function parseFlag(item: string): { verdict: Verdict; text: string } {
  const s = item.replace(/^⚠\s*/, "").trim();
  if (/\[entailment:\s*refuted\]/i.test(s)) return { verdict: "refuted", text: s.replace(/\[entailment:\s*refuted\]\s*/i, "") };
  if (/\[entailment:\s*not-enough-info\]/i.test(s)) return { verdict: "nei", text: s.replace(/\[entailment:\s*not-enough-info\]\s*/i, "") };
  if (/\[conflict[^\]]*\]/i.test(s)) return { verdict: "conflict", text: s.replace(/\[conflict[^\]]*\]\s*/i, "") };
  if (/\[verifier:\s*corrected\]/i.test(s)) return { verdict: "corrected", text: s.replace(/\[verifier:\s*corrected\]\s*/i, "") };
  if (/\[verifier:\s*contradicted\]/i.test(s)) return { verdict: "contradicted", text: s.replace(/\[verifier:\s*contradicted\]\s*/i, "") };
  if (/\[verifier:\s*weak\]/i.test(s)) return { verdict: "weak", text: s.replace(/\[verifier:\s*weak\]\s*/i, "") };
  if (/\[link dead\]/i.test(s)) return { verdict: "link-dead", text: s.replace(/\[link dead\]\s*/i, "") };
  if (/single-source/i.test(s)) return { verdict: "single-source", text: s.replace(/single-source[^:]*:\s*/i, "") };
  return { verdict: "unsupported", text: s };
}

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex flex-col" style={{ minWidth: 76 }}>
      <span style={{ fontSize: 20, fontWeight: 700, color: color ?? "var(--text)", lineHeight: 1.1 }}>{value}</span>
      <span style={{ fontSize: 11, color: "var(--faint)" }}>{label}</span>
    </div>
  );
}

function TrustSummary({ trust }: { trust: Trust }) {
  const e = trust.engine;
  const uh = trust.url_health;
  const engineLabel = e === "entailment" ? "Entailment NLI" : e === "embedding" ? "Embedding grounding" : null;
  const total = (trust.supported ?? 0) + (trust.refuted ?? 0) + (trust.nei ?? 0);
  return (
    <div className="flex flex-col gap-3" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12 }}>
      {engineLabel && (
        <span className="tag" style={{ alignSelf: "flex-start" }}>
          {engineLabel}{total ? ` · ${total} claims checked` : ""}
        </span>
      )}
      <div className="flex flex-wrap gap-5">
        {e === "entailment" && <Stat label="Supported" value={trust.supported ?? 0} color="#34D399" />}
        {e === "entailment" && (trust.refuted ?? 0) > 0 && <Stat label="Refuted" value={trust.refuted ?? 0} color="#FB7185" />}
        {e === "entailment" && (trust.nei ?? 0) > 0 && <Stat label="Not enough info" value={trust.nei ?? 0} color="#FBBF24" />}
        {(trust.conflicts ?? 0) > 0 && <Stat label="Source conflicts" value={trust.conflicts ?? 0} color="#C084FC" />}
        {typeof trust.consensus === "number" && <Stat label="Corroborated" value={`${Math.round(trust.consensus * 100)}%`} />}
        {uh && uh.total > 0 && (
          <Stat label="Links live" value={`${uh.live}/${uh.total}`} color={uh.dead > 0 ? "#FB7185" : "#34D399"} />
        )}
      </div>
    </div>
  );
}

export function TrustPanel({ flagged, trust }: { flagged: string[]; trust?: Trust }) {
  const hasSummary = !!trust && !!trust.engine && trust.engine !== "none";
  const e = trust?.engine;
  const claimsChecked = (trust?.supported ?? 0) + (trust?.refuted ?? 0) + (trust?.nei ?? 0);
  // The all-clear may ONLY show when the entailment judge actually ran on cited claims. A cosine-only
  // fallback (engine "embedding") or a run with nothing checked must not read as "fully verified".
  const verified = e === "entailment" && claimsChecked > 0;
  const degraded = trust?.assurance === "reduced" || (!!e && e !== "entailment");
  return (
    <div className="card flex flex-col gap-3" aria-label="verification and trust">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">🛡️ Verification &amp; trust</h3>
        <span className="tag">{flagged.length} flagged</span>
      </div>
      {hasSummary && <TrustSummary trust={trust!} />}
      {!!trust?.conflict_items?.length && (
        <div className="flex flex-col gap-1" style={{ fontSize: 13 }}>
          <span style={{ color: "#C084FC", fontWeight: 600 }}>Cross-source conflicts</span>
          <ul className="flex flex-col gap-1" style={{ paddingLeft: 16, color: "var(--muted)", listStyle: "disc" }}>
            {trust!.conflict_items!.slice(0, 6).map((c, i) => (
              <li key={i} style={{ wordBreak: "break-word" }}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {degraded && (
        <p className="text-sm" role="status" style={{ color: "#FBBF24" }}>
          ⚠ Reduced assurance: similarity-only grounding (no per-claim NLI verdicts) — treat this result as less certain.
        </p>
      )}
      {flagged.length === 0 ? (
        verified ? (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            ✓ Every cited claim got an entailment verdict, a cross-source agreement check, and a live-link probe — none were left unsupported.
          </p>
        ) : (
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Not independently verified — the per-claim entailment judge did not run on this report.
          </p>
        )
      ) : (
        <ul className="flex flex-col gap-2">
          {flagged.map((item, i) => {
            const { verdict, text } = parseFlag(item);
            const b = BADGES[verdict];
            return (
              <li key={i} className="flex gap-2 items-start text-sm">
                <span style={{
                  color: b.color, border: `1px solid ${b.color}`, borderRadius: 6,
                  padding: "1px 7px", fontSize: 11, fontWeight: 700, whiteSpace: "nowrap", marginTop: 1,
                }}>{b.label}</span>
                <span style={{ color: "var(--muted)", wordBreak: "break-word" }}>{text}</span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-xs" style={{ color: "var(--faint)" }}>
        Each cited claim gets a directional entailment verdict (Supported / Refuted / Not-Enough-Info), a
        cross-source conflict check, and a live-link probe — an auditable trust ledger, not just a similarity score.
      </p>
    </div>
  );
}
