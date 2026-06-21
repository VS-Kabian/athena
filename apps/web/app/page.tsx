"use client";
import { useState, useEffect } from "react";
import { ModelPicker } from "@/components/providers/ModelPicker";
import { SearchPicker } from "@/components/providers/SearchPicker";
import { RoundsSlider } from "@/components/research/RoundsSlider";
import { StartCancel } from "@/components/research/StartCancel";
import { StatusPanel } from "@/components/research/StatusPanel";
import { ResearchGraph } from "@/components/research/ResearchGraph";
import { ReportView } from "@/components/report/ReportView";
import { QualityBreakdown } from "@/components/report/QualityBreakdown";
import { SourceList, type ReportSource } from "@/components/report/SourceList";
import { TrustPanel } from "@/components/report/TrustPanel";
import { DownloadBar } from "@/components/report/DownloadBar";
import { CoveragePanel } from "@/components/research/CoveragePanel";
import { useResearchStream } from "@/lib/sse";
import { startResearch, cancelResearch, getRun, getPlan } from "@/lib/api";
import type { LLMSpec, SearchSpec, Citation, QualityBreakdown as QB, Trust } from "@/lib/types";

export default function Home() {
  const [topic, setTopic] = useState("");
  const [llm, setLlm] = useState<LLMSpec | null>(null);
  const [search, setSearch] = useState<SearchSpec>({ providers: ["ddg", "searxng"], mode: "broadcast", keys: {} });
  const [rounds, setRounds] = useState(2);
  const [deep, setDeep] = useState(false);
  const [llmFast, setLlmFast] = useState<LLMSpec | null>(null);
  const [reportType, setReportType] = useState("standard");
  const [verifier, setVerifier] = useState<LLMSpec | null>(null);
  const [patient, setPatient] = useState(false);
  const [plan, setPlan] = useState<string[] | null>(null);
  const [planning, setPlanning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const stream = useResearchStream(runId);
  const running = !!runId && !stream.done;
  const [report, setReport] = useState<string | null>(null);
  const [reportSources, setReportSources] = useState<ReportSource[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [breakdown, setBreakdown] = useState<QB | null>(null);
  const [flagged, setFlagged] = useState<string[]>([]);
  const [trust, setTrust] = useState<Trust | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    // only pull the report on success (or cancel — partial); never on a failed run (no report exists)
    if ((stream.phase === "done" || stream.phase === "cancelled") && runId) getRun(runId).then((d) => {
      setReport(d.report); setReportSources(d.sources ?? []);
      setCitations(d.citations ?? []); setBreakdown(d.quality_breakdown ?? null);
      setFlagged(d.flagged ?? []); setTrust(d.trust ?? null);
    }).catch(() => {});   // transient fetch error: keep whatever's shown rather than blanking it
  }, [stream.phase, runId]);

  async function onStart() {
    if (!llm || !topic || submitting) return;   // guard against rapid double-submit (two server runs)
    setStartError(null); setSubmitting(true);
    // clear the previous run's report up front, so a FAILED start can't leave a stale report on screen
    setReport(null); setReportSources([]); setCitations([]); setBreakdown(null); setFlagged([]); setTrust(null);
    try {
      const editedPlan = plan ? plan.map((q) => q.trim()).filter(Boolean) : undefined;
      const { run_id } = await startResearch({ topic, rounds, llm, search, deep,
        llm_fast: llmFast, report_type: reportType, verifier, patient,
        plan: editedPlan && editedPlan.length ? editedPlan : undefined });
      if (!run_id) throw new Error("The server didn't return a run id.");
      setRunId(run_id);
      try {
        const h = JSON.parse(localStorage.getItem("athena:history") || "[]");
        h.unshift({ id: run_id, topic, ts: Date.now() });
        localStorage.setItem("athena:history", JSON.stringify(h.slice(0, 50)));
      } catch {}
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Couldn't start research — is the API running?");
    } finally {
      setSubmitting(false);
    }
  }
  async function onCancel() {
    if (!runId) return;
    // best-effort: even if the cancel request fails, the SSE watchdog will eventually unstick the UI
    try { await cancelResearch(runId); } catch {}
  }
  async function onPreviewPlan() {
    if (!llm || !topic) return;
    setPlanning(true);
    try { const r = await getPlan({ topic, llm, llm_fast: llmFast }); setPlan(r.sub_questions ?? []); }
    catch (e) { setPlan(null); setStartError(e instanceof Error ? e.message : "Couldn't build a plan — check the model / API."); }
    finally { setPlanning(false); }
  }

  return (
    <div className="research-page flex flex-col gap-8">
      <header>
        <h1 className="page-title">New Research</h1>
        <p className="page-sub">Autonomous multi-round deep research across the open web.</p>
      </header>

      <div className="card composer-card" style={{ padding: 0, overflow: "hidden" }}>
        <textarea className="composer" aria-label="topic" rows={3} disabled={running}
          placeholder="Research anything…  e.g.  What is the Model Context Protocol (MCP)?"
          value={topic} onChange={(e) => setTopic(e.target.value)} />
      </div>

      <div className="settings-grid">
        <div className="card setting"><div className="card-label">Model</div><ModelPicker onChange={setLlm} disabled={running} /></div>
        <div className="card setting"><div className="card-label">Search providers</div><SearchPicker onChange={setSearch} disabled={running} /></div>
        <div className="card setting"><div className="card-label">Depth</div><RoundsSlider onChange={setRounds} disabled={running} /></div>
        <div className="card setting">
          <div className="card-label">Report type</div>
          <select className="field" aria-label="report type" value={reportType} disabled={running}
            onChange={(e) => setReportType(e.target.value)}>
            <option value="standard">Standard</option>
            <option value="literature-review">Literature review</option>
            <option value="comparison">Comparison</option>
            <option value="how-to">How-to guide</option>
            <option value="market-scan">Market scan</option>
          </select>
        </div>
        <div className="card setting">
          <div className="card-label">Fast model — optional</div>
          <ModelPicker onChange={setLlmFast} disabled={running} />
          <span style={{ fontSize: 12, color: "var(--faint)", marginTop: 8, display: "block" }}>
            Routes planning &amp; reflection to a faster model on deep / 5-round runs.
          </span>
        </div>
        <div className="card setting">
          <div className="card-label">Verifier model — 2nd model (optional)</div>
          <ModelPicker onChange={setVerifier} disabled={running} />
          <span style={{ fontSize: 12, color: "var(--faint)", marginTop: 8, display: "block" }}>
            A second model cross-checks &amp; corrects claims. Use a different provider for best results.
          </span>
        </div>
      </div>

      <label className="flex items-center gap-2" aria-label="deep mode"
        style={{ fontSize: 13.5, color: "var(--muted)", cursor: "pointer", userSelect: "none" }}>
        <input type="checkbox" checked={deep} disabled={running}
          onChange={(e) => setDeep(e.target.checked)} />
        <span><strong style={{ color: "var(--text)" }}>Deep mode</strong> — the agent reflects after each round and may stop early or drill into gaps</span>
      </label>

      <label className="flex items-center gap-2" aria-label="patient mode"
        style={{ fontSize: 13.5, color: "var(--muted)", cursor: "pointer", userSelect: "none" }}>
        <input type="checkbox" checked={patient} disabled={running}
          onChange={(e) => setPatient(e.target.checked)} />
        <span><strong style={{ color: "var(--text)" }}>Patient mode</strong> — allow slow models to run longer (up to ~45 min)</span>
      </label>

      {plan !== null && (
        <div className="card" aria-label="research plan" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="card-label" style={{ marginBottom: 2 }}>Research plan — edit the sub-questions before running</div>
          {plan.length === 0 && <span style={{ fontSize: 13, color: "var(--faint)" }}>No sub-questions — add one below, or just Start to auto-plan.</span>}
          {plan.map((q, i) => (
            <div key={i} className="flex gap-2 items-center">
              <span style={{ color: "var(--faint)", fontFamily: "var(--font-mono)", fontSize: 12, width: 18 }}>{i + 1}</span>
              <input className="field" aria-label={`sub-question ${i + 1}`} value={q}
                onChange={(e) => setPlan(plan.map((x, j) => (j === i ? e.target.value : x)))} />
              <button className="btn-ghost btn-sm" aria-label={`remove ${i + 1}`} disabled={running}
                onClick={() => setPlan(plan.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <button className="btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} disabled={running}
            onClick={() => setPlan([...plan, ""])}>+ Add sub-question</button>
        </div>
      )}

      <div className="flex gap-3 items-center flex-wrap">
        <button className="btn-ghost" disabled={!llm || !topic || planning || running} onClick={onPreviewPlan}>
          {planning ? "Planning…" : plan !== null ? "Re-plan" : "Preview plan"}
        </button>
        <StartCancel canStart={!!llm && !!topic && !submitting} running={running} onStart={onStart} onCancel={onCancel} />
      </div>

      {startError && (
        <div className="card" role="alert" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          ⚠ {startError}
        </div>
      )}

      {runId && stream.related.length > 0 && (
        <div className="card" aria-label="related prior research" style={{ fontSize: 13 }}>
          <div className="card-label">Related prior research</div>
          <div className="flex flex-wrap gap-2" style={{ marginTop: 6 }}>
            {stream.related.map((r, i) => (
              <span key={i} className="tag" title={`similarity ${r.similarity}`}>{r.topic}</span>
            ))}
          </div>
        </div>
      )}

      {runId && (
        <section className="live-grid">
          <StatusPanel status={stream.status} round={stream.round} roundsTotal={rounds}
            discovered={stream.discovered} validated={stream.validated}
            model={llm?.model ?? ""} providers={search.providers} running={running} quality={stream.quality} />
          <ResearchGraph topic={topic} sources={stream.sources} status={stream.status} />
        </section>
      )}

      {runId && stream.coverage && stream.coverage.cells.length > 0 && (
        <CoveragePanel coverage={stream.coverage} entail={stream.entail} urlHealth={stream.urlHealth} />
      )}

      {runId && running && stream.draft && (
        <section className="flex flex-col gap-2" aria-label="report draft">
          <div className="card-label">Writing report…</div>
          <ReportView markdown={stream.draft} citations={[]} />
        </section>
      )}

      {runId && stream.usage && stream.usage.total_tokens != null && (
        <div style={{ fontSize: 12.5, color: "var(--faint)", fontFamily: "var(--font-mono)" }}>
          {stream.usage.total_tokens.toLocaleString()} tokens
          {stream.usage.cost != null ? ` · ~$${stream.usage.cost.toFixed(4)}` : ""}
        </div>
      )}

      {runId && stream.verify && (
        <div className="card" aria-label="verification" style={{ fontSize: 13 }}>
          <div className="card-label">Second-model verification</div>
          <div style={{ marginTop: 6, color: "var(--muted)" }}>
            {stream.verify.contested} claim(s) corrected or flagged by the verifier model.
          </div>
        </div>
      )}

      {runId && stream.reflections.length > 0 && (
        <div className="card" aria-label="agent reflections" style={{ fontSize: 13 }}>
          <div className="card-label">Agent reasoning</div>
          <ul style={{ marginTop: 6, paddingLeft: 18, color: "var(--muted)" }}>
            {stream.reflections.map((r, i) => (
              <li key={i}><strong style={{ color: "var(--text)" }}>Round {r.round} · {r.action}</strong>{r.reason ? ` — ${r.reason}` : ""}</li>
            ))}
          </ul>
        </div>
      )}

      {runId && stream.phase === "failed" && (
        <div className="card" role="alert" style={{ borderColor: "var(--bad)", color: "var(--bad)" }}>
          ⚠ {stream.error || "Research failed."}
          <button className="btn-ghost btn-sm" style={{ marginLeft: 12 }} disabled={running} onClick={onStart}>Start again</button>
        </div>
      )}

      {runId && stream.phase === "cancelled" && !report && (
        <div className="card" role="alert" style={{ color: "var(--muted)" }}>Research cancelled — no report was produced.</div>
      )}

      {runId && (stream.phase === "done" || (stream.phase === "cancelled" && report)) && (
        <section className="flex flex-col gap-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h2 className="page-title" style={{ fontSize: 22 }}>
              Report{stream.phase === "cancelled" ? " (partial — cancelled)" : ""}
            </h2>
            <DownloadBar runId={runId} />
          </div>
          {report && <ReportView markdown={report} citations={citations} />}
          {breakdown && <QualityBreakdown breakdown={breakdown} />}
          {report && <TrustPanel flagged={flagged} trust={trust ?? undefined} />}
          <SourceList sources={reportSources} urlStatus={trust?.url_status ?? {}} />
        </section>
      )}
    </div>
  );
}
