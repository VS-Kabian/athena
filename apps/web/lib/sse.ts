import { useEffect, useRef, useState } from "react";
import type { SourceEvent, Coverage, EntailSummary, UrlHealth } from "./types";

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
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) return;
    setStatus("Starting"); setDone(false); setSources([]); setRound(0); setDiscovered(0); setValidated(0); setQuality(null);
    setReflections([]); setRelated([]); setVerify(null); setPhase("running"); setError(null); setDraft(""); setReasoning(""); setUsage(null);
    setCoverage(null); setEntail(null); setUrlHealth(null);
    const token = streamToken();
    // This URL never carries an existing query string, so a bare `?token=` separator is safe.
    const url = `${BASE}/api/research/${runId}/stream`
      + (token ? `?token=${encodeURIComponent(token)}` : "");
    const es = new EventSource(url);
    esRef.current = es;

    // Inactivity watchdog: native EventSource silently reconnects forever (readyState stays
    // CONNECTING), so a dead backend / proxy timeout would otherwise pin the UI to "running" with
    // no escape. If no event arrives for INACTIVITY_MS, surface a failure so the user can recover.
    // The backend emits a `heartbeat` every ~20s, so a healthy run (even a long silent synthesis on a
    // reasoning model) keeps resetting this; only a truly dead stream trips it.
    const INACTIVITY_MS = 120_000;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    const stopWatchdog = () => { if (watchdog) clearTimeout(watchdog); watchdog = undefined; };
    const armWatchdog = () => {
      stopWatchdog();
      watchdog = setTimeout(() => {
        setStatus("Connection timed out");
        setError("The server stopped responding. The run may still be going — reload to reconnect.");
        setDone(true); setPhase("failed"); es.close();
      }, INACTIVITY_MS);
    };

    const on = (t: string, fn: (e: MessageEvent) => void) =>
      es.addEventListener(t, (e) => { armWatchdog(); fn(e as MessageEvent); });
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
    on("done", () => { stopWatchdog(); setStatus("Done"); setDone(true); setPhase("done"); es.close(); });
    on("cancelled", () => { stopWatchdog(); setStatus("Cancelled"); setDone(true); setPhase("cancelled"); es.close(); });
    on("failed", (e) => {
      stopWatchdog();
      let msg = "Research failed";
      try { msg = JSON.parse(e.data).message || msg; } catch {}
      setStatus(msg); setError(msg); setDone(true); setPhase("failed"); es.close();
    });
    // Native EventSource connection error: only terminal if the connection is actually closed
    // (transient reconnects keep readyState === CONNECTING and must NOT end a healthy run).
    let closed = false;
    es.addEventListener("error", () => {
      if (closed) return;   // we closed it on purpose (unmount / new run) — not a real failure
      if (es.readyState === EventSource.CLOSED) {
        stopWatchdog();
        setStatus("Connection lost"); setError("Connection lost"); setDone(true); setPhase("failed");
      }
    });
    armWatchdog();                                  // start the clock now (covers a never-connects stall)
    return () => { closed = true; stopWatchdog(); es.close(); };
  }, [runId]);

  return { status, round, discovered, validated, sources, done, quality, reflections, related, verify, coverage, entail, urlHealth, phase, error, draft, reasoning, usage };
}
