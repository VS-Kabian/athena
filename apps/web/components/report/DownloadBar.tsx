"use client";
import { useState } from "react";
import { downloadReport } from "@/lib/api";

export function DownloadBar({ runId }: { runId: string }) {
  const [busy, setBusy] = useState<"md" | "pdf" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function dl(fmt: "md" | "pdf") {
    setErr(null); setBusy(fmt);
    try { await downloadReport(runId, fmt); }
    catch (e) { setErr(e instanceof Error ? e.message : "Download failed"); }
    finally { setBusy(null); }
  }

  return (
    <div className="flex gap-3 items-center" aria-label="downloads">
      <button className="btn-ghost btn-sm" disabled={busy !== null} onClick={() => dl("md")}>
        {busy === "md" ? "Downloading…" : "Download .md"}
      </button>
      <button className="btn-ghost btn-sm" disabled={busy !== null} onClick={() => dl("pdf")}>
        {busy === "pdf" ? "Downloading…" : "Download .pdf"}
      </button>
      {err && <span role="alert" style={{ color: "var(--bad)", fontSize: 12 }}>{err}</span>}
    </div>
  );
}
