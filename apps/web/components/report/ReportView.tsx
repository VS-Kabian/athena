"use client";
import ReactMarkdown from "react-markdown";
import { CitationChip } from "./CitationChip";
import type { Citation } from "@/lib/types";
import { safeHref } from "@/lib/safeHref";

export function ReportView({ markdown, citations = [] }: { markdown: string; citations?: Citation[] }) {
  const byN: Record<number, Citation> = {};
  for (const c of citations) byN[c.n] = c;
  // turn ONLY real citation markers [n] into links; leave array indices like arr[0] untouched
  const processed = markdown.replace(/\[(\d+)\]/g, (full, n) => (byN[Number(n)] ? `[${n}](#cite-${n})` : full));
  return (
    <article className="glass report" aria-label="report" style={{ display: "block" }}>
      <ReactMarkdown
        components={{
          a: ({ href, children }) => {
            const m = /^#cite-(\d+)$/.exec(href || "");
            if (m) { const n = Number(m[1]); return <CitationChip n={n} citation={byN[n]} />; }
            return <a href={safeHref(href)} target="_blank" rel="noreferrer">{children}</a>;
          },
        }}
      >
        {processed}
      </ReactMarkdown>
    </article>
  );
}
