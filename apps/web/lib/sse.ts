import { useEffect, useRef, useState } from "react";
import type { SourceEvent, Coverage, EntailSummary, UrlHealth, InlineReport } from "./types";

const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:7000";

// EventSource can't set an Authorization header, so the backend accepts the shared-secret token
// as a `?token=` query param on the stream. Mirror the localStorage key used by lib/api.ts.
// Unset on localhost -> no param -> open API, no friction.
function streamToken(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem("athena:api_token");
}

export function useResearchStream(runId: string | null) {
  const [status, setStatus] = useState("idle");
  const [round, setRound] = useState(0);
  const [discovered, setDiscovered] = useState(0);
  const [validated, setValidated] = useState(0);
  const [sources, setSources] = useState<SourceEvent[]>([]);
  const [done, setDone] = useState(false);
  const [quality, setQuality] = useState<{ score: number; risk: number; consensus?: number } | null>(null);
  const [reflections, setReflections] = useState<{ round: number; action: string; reason: string }[]>([]);
  const [related, setRelated] = useState<{ topic: string; similarity: number }[]>([]);
  const [verify, setVerify] = useState<{ contested: number } | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [entail, setEntail] = useState<EntailSummary | null>(null);
  const [urlHealth, setUrlHealth] = useState<UrlHealth | null>(null);
  const [phase, setPhase] = useState<"running" | "done" | "failed" | "cancelled">("running");
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [usage, setUsage] = useState<{ total_tokens?: number; cost?: number } | null>(null);
  const [reportReady, setReportReady] = useState(true);              // false => DB persist failed at finish
  const [inlineReport, setInlineReport] = useState<InlineReport | null>(null);  // P0-4 fallback payload
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) return;
    setStatus("Starting"); setDone(false); setSources([]); setRound(0); setDiscovered(0); setValidated(0); setQuality(null);
    setReflections([]); setRelated([]); setVerify(null); setPhase("running"); setError(null); setDraft(""); setReasoning(""); setUsage(null);
    setCoverage(null); setEntail(null); setUrlHealth(null); setReportReady(true); setInlineReport(null);
    const token = streamToken();
    const base = `${BASE}/api/research/${runId}/stream`
      + (token ? `?token=${encodeURIComponent(token)}` : "");

    // Inactivity watchdog: native EventSource silently reconnects forever (readyState stays
    // CONNECTING), so a dead backend / proxy timeout would otherwise pin the UI to "running" with
    // no escape. If no event arrives for INACTIVITY_MS, surface a failure so the user can recover.
    const INACTIVITY_MS = 120_000;
    const MAX_RECONNECTS = 3;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    let lastId: string | null = null;   // last SSE id received -> resume from here on reconnect (P2-5)
    let reconnects = 0;
    let closed = false;
    const stopWatchdog = () => { if (watchdog) clearTimeout(watchdog); watchdog = undefined; };

    const connect = () => {
      // resume from the last received id so a reconnect delivers only NEWER events (no full replay)
      const url = base + (lastId ? `${token ? "&" : "?"}lastEventId=${encodeURIComponent(lastId)}` : "");
      const es = new EventSource(url);
      esRef.current = es;

      const armWatchdog = () => {
        stopWatchdog();
        watchdog = setTimeout(() => {
          setStatus("Connection timed out");
          setError("The server stopped responding. The run may still be going — reload to reconnect.");
          setDone(true); setPhase("failed"); es.close();
        }, INACTIVITY_MS);
      };

      const on = (t: string, fn: (e: MessageEvent) => void) =>
        es.addEventListener(t, (e) => {
          armWatchdog();
          reconnects = 0;                            // a delivered event = healthy connection
          const me = e as MessageEvent;
          if (me.lastEventId) lastId = me.lastEventId;
          fn(me);
        });
      on("round_start", (e) => { const d = JSON.parse(e.data); setRound(d.round); setStatus(`Round ${d.round}`); });
      on("source", (e) => setSources((s) => [...s, JSON.parse(e.data)]));
      on("progress", (e) => setDiscovered(JSON.parse(e.data).discovered));
      on("validated", (e) => setValidated(JSON.parse(e.data).count));
      on("quality", (e) => { const d = JSON.parse(e.data); setQuality({ score: d.score, risk: d.hallucination_risk, consensus: d.consensus }); });
      on("reading", (e) => { const d = JSON.parse(e.data); setStatus(`Reading ${d.count} sources · round ${d.round}`); });
      on("reflect", (e) => { const d = JSON.parse(e.data); setReflections((r) => [...r, d]); setStatus(`Reflecting · round ${d.round}`); });
      on("memory", (e) => { const d = JSON.parse(e.data); setRelated(d.related ?? []); });
      on("verify", (e) => { const d = JSON.parse(e.data); setVerify({ contested: d.contested ?? 0 }); });
      on("coverage", (e) => { setCoverage(JSON.parse(e.data)); });
      on("entail", (e) => { setEntail(JSON.parse(e.data)); });
      on("urlhealth", (e) => { setUrlHealth(JSON.parse(e.data)); });
      on("heartbeat", () => {});   // keepalive: the on() wrapper re-arms the inactivity watchdog
      on("fetching", (e) => { const d = JSON.parse(e.data); setStatus(`Reading ${d.count} sources`); });
      on("synthesizing", () => setStatus("Synthesizing report"));
      on("report_delta", (e) => { const d = JSON.parse(e.data); setDraft((x) => x + (d.text ?? "")); });
      on("reasoning_delta", (e) => { const d = JSON.parse(e.data); setReasoning((x) => x + (d.text ?? "")); });
      on("usage", (e) => setUsage(JSON.parse(e.data)));
      on("done", (e) => {
        stopWatchdog();
        // capture report_ready + the inline fallback report (P0-4) so the page can render even if the DB read fails
        try { const d = JSON.parse(e.data); setReportReady(d.report_ready !== false); setInlineReport(d.report ?? null); } catch {}
        setStatus("Done"); setDone(true); setPhase("done"); es.close();
      });
      on("cancelled", () => { stopWatchdog(); setStatus("Cancelled"); setDone(true); setPhase("cancelled"); es.close(); });
      on("failed", (e) => {
        stopWatchdog();
        let msg = "Research failed";
        try { msg = JSON.parse(e.data).message || msg; } catch {}
        setStatus(msg); setError(msg); setDone(true); setPhase("failed"); es.close();
      });
      // Connection error. Only act when actually CLOSED (transient reconnects keep CONNECTING). On a real
      // close, try a bounded manual reconnect (resuming from lastId) before declaring failure (P2-5).
      es.addEventListener("error", () => {
        if (closed) return;   // we closed it on purpose (unmount / new run) — not a real failure
        if (es.readyState === EventSource.CLOSED) {
          es.close();
          if (reconnects < MAX_RECONNECTS) {
            reconnects += 1;
            setStatus(`Reconnecting… (${reconnects})`);
            connect();        // resume from lastId
          } else {
            stopWatchdog();
            setStatus("Connection lost"); setError("Connection lost"); setDone(true); setPhase("failed");
          }
        }
      });
      armWatchdog();          // start the clock now (covers a never-connects stall)
    };

    connect();
    return () => { closed = true; stopWatchdog(); esRef.current?.close(); };
  }, [runId]);

  return { status, round, discovered, validated, sources, done, quality, reflections, related, verify, coverage, entail, urlHealth, phase, error, draft, reasoning, usage, reportReady, inlineReport };
}
