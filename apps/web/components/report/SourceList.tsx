"use client";
import { safeHref } from "@/lib/safeHref";

export type ReportSource = { url: string; title: string; source_type: string; round: number; validated?: boolean };

const TYPE_LABEL: Record<string, string> = {
  web: "Web", paper: "Papers", github: "GitHub", blog: "Blogs", docs: "Docs", news: "News",
};

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  dead: { label: "dead link", color: "#FB7185" },
  unreachable: { label: "unreachable", color: "#FBBF24" },
};

export function SourceList({ sources, urlStatus = {} }: { sources: ReportSource[]; urlStatus?: Record<string, string> }) {
  const groups: Record<string, ReportSource[]> = {};
  for (const s of sources) (groups[s.source_type] ??= []).push(s);
  return (
    <div className="card flex flex-col gap-4" aria-label="sources">
      <h3 className="font-semibold">Sources ({sources.length})</h3>
      {sources.length === 0 && (
        <p className="text-sm" style={{ color: "var(--muted)" }}>No sources were collected for this run.</p>
      )}
      {Object.entries(groups).map(([type, items]) => (
        <div key={type} className="flex flex-col gap-1">
          <div className="card-label" style={{ margin: "0 0 8px" }}>
            {TYPE_LABEL[type] ?? type}
          </div>
          <ul className="flex flex-col gap-1">
            {items.map((s) => {
              const status = urlStatus[s.url];
              const badge = STATUS_BADGE[status];
              const dead = status === "dead";
              const label = `${s.validated ? "✓ " : ""}${s.title || s.url}`;
              return (
                <li key={s.url} className="text-sm">
                  {dead ? (
                    // a dead/fabricated citation URL is NOT made clickable — clicking it just hits a broken
                    // page; render it as plain struck-through text so the reader sees it was a source but gone (P3).
                    <span style={{ color: "var(--faint)", textDecoration: "line-through" }}
                      title="This source URL is dead — not linked">{label}</span>
                  ) : (
                    <a href={safeHref(s.url)} target="_blank" rel="noreferrer" className="hover:underline">{label}</a>
                  )}
                  <span className="text-xs ml-2" style={{ color: "var(--muted)" }}>R{s.round}</span>
                  {badge && (
                    <span className="text-xs ml-2" style={{
                      color: badge.color, border: `1px solid ${badge.color}`, borderRadius: 5,
                      padding: "0 6px", fontWeight: 600,
                    }}>{badge.label}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
