"use client";
import { useEffect, useRef } from "react";
import type { SourceEvent } from "@/lib/types";

// Custom canvas animation of the live research: a central ATHENA core, one sub-agent hub per facet,
// sources that fly in and orbit their agent, with data flowing along the links. Pan (drag), zoom
// (wheel), hover-for-details, and a Fit button. Replaces react-force-graph (whose fixed-height vs
// stretched-container mismatch produced a smeared duplicate band).

const TYPE_COLORS: Record<string, string> = {
  web: "#38BDF8", paper: "#34D399", github: "#F472B6", blog: "#FBBF24",
  docs: "#22D3EE", news: "#FB7185", hop: "#C084FC",
};
const ENGINE_COLORS: Record<string, string> = {
  ddg: "#FBBF24", searxng: "#38BDF8", tavily: "#34D399", serper: "#A78BFA",
  specialist: "#F472B6", hop: "#C084FC",
};
const FALLBACK = ["#A78BFA", "#38BDF8", "#34D399", "#FBBF24", "#F472B6", "#22D3EE", "#FB7185", "#C084FC"];
const STAGES = ["Plan", "Search", "Read", "Synthesize", "Verify"];

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c] as string));

function stageIndex(status?: string): number {
  const s = (status || "").toLowerCase();
  if (s.includes("done") || s.includes("complete") || s.includes("verif")) return 4;
  if (s.includes("synth")) return 3;
  if (s.includes("reading") || s.includes("fetch")) return 2;
  if (s.includes("round") || s.includes("reflect") || s.includes("searching")) return 1;
  return 0;
}

// the actual search engine the agent used to reach this source
const groupKey = (s: SourceEvent): string => (s.providers && s.providers[0]) || s.provider || "web";

// group sources by the search engine that found them; overflow folds into the least-filled hub
function groupSources(sources: SourceEvent[]): [string, SourceEvent[]][] {
  const order: string[] = [];
  const m = new Map<string, SourceEvent[]>();
  for (const s of sources) {
    let key = groupKey(s);
    if (!m.has(key)) {
      if (order.length < 8) { m.set(key, []); order.push(key); }
      else key = order.reduce((a, b) => (m.get(a)!.length <= m.get(b)!.length ? a : b));
    }
    m.get(key)!.push(s);
  }
  return order.map((k) => [k, m.get(k)!]);
}

type Dot = {
  id: string; x: number; y: number; tx: number; ty: number; a: number;
  color: string; r: number; kind: "core" | "agent" | "source"; label: string; sub: string; href?: string;
};
type Link = { from: string; to: string; color: string };

export function ResearchGraph({ topic, sources, status }:
  { topic: string; sources: SourceEvent[]; status?: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const dataRef = useRef<{ sources: SourceEvent[]; topic: string }>({ sources, topic });
  dataRef.current = { sources, topic };
  const viewRef = useRef({ scale: 1, ox: 0, oy: 0 });

  useEffect(() => {
    const canvas = canvasRef.current, wrap = wrapRef.current, tip = tipRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;   // jsdom / no-canvas env -> render the shell only, no crash

    const reduced = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const dots = new Map<string, Dot>();
    let links: Link[] = [];
    let raf = 0, t = 0, W = 0, H = 0;
    let drag: { mx: number; my: number; ox: number; oy: number } | null = null;

    const resize = () => {
      W = wrap.clientWidth; H = wrap.clientHeight;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      canvas.style.width = W + "px"; canvas.style.height = H + "px";
    };
    resize();
    const ro = new ResizeObserver(resize); ro.observe(wrap);

    const ensure = (id: string, init: Partial<Dot> & Pick<Dot, "kind">): Dot => {
      let d = dots.get(id);
      if (!d) { d = { id, x: W / 2, y: H / 2, tx: W / 2, ty: H / 2, a: 0, color: "#fff", r: 3, label: "", sub: "", ...init }; dots.set(id, d); }
      return d;
    };
    const toWorld = (mx: number, my: number) => ({ x: (mx - viewRef.current.ox) / viewRef.current.scale, y: (my - viewRef.current.oy) / viewRef.current.scale });
    const dotAt = (mx: number, my: number): Dot | undefined => {
      const w = toWorld(mx, my); const tol = 6 / viewRef.current.scale;
      let best: Dot | undefined, bd = 1e9;
      dots.forEach((d) => { const dist = Math.hypot(d.x - w.x, d.y - w.y); if (dist < d.r + tol && dist < bd) { bd = dist; best = d; } });
      return best;
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect(); const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const v = viewRef.current; const w = toWorld(mx, my);
      v.scale = Math.max(0.4, Math.min(4, v.scale * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      v.ox = mx - w.x * v.scale; v.oy = my - w.y * v.scale;
    };
    const onDown = (e: MouseEvent) => { drag = { mx: e.clientX, my: e.clientY, ox: viewRef.current.ox, oy: viewRef.current.oy }; canvas.style.cursor = "grabbing"; };
    const onUp = () => { drag = null; canvas.style.cursor = "grab"; };
    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect(); const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      if (drag) { viewRef.current.ox = drag.ox + (e.clientX - drag.mx); viewRef.current.oy = drag.oy + (e.clientY - drag.my); if (tip) tip.style.display = "none"; return; }
      const d = dotAt(mx, my);
      if (d && tip) {
        tip.style.display = "block"; tip.style.left = mx + 14 + "px"; tip.style.top = my + 14 + "px";
        tip.innerHTML = `<b>${esc(d.label)}</b>${d.sub ? `<br><span style="opacity:.62">${esc(d.sub)}</span>` : ""}`;
        canvas.style.cursor = d.href ? "pointer" : "grab";
      } else if (tip) { tip.style.display = "none"; canvas.style.cursor = "grab"; }
    };
    const onLeave = () => { if (tip) tip.style.display = "none"; drag = null; };
    const onClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect(); const d = dotAt(e.clientX - rect.left, e.clientY - rect.top);
      if (d && d.href) window.open(d.href, "_blank", "noopener,noreferrer");
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("mousedown", onDown); window.addEventListener("mouseup", onUp);
    canvas.addEventListener("mousemove", onMove); canvas.addEventListener("mouseleave", onLeave);
    canvas.addEventListener("click", onClick);

    const drawDot = (d: Dot, glow: number) => {
      const al = Math.max(0, Math.min(1, d.a));
      ctx.save(); ctx.globalAlpha = al; ctx.shadowColor = d.color; ctx.shadowBlur = glow;
      ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, 2 * Math.PI); ctx.fillStyle = d.color; ctx.fill();
      ctx.restore();
      ctx.globalAlpha = al;
      ctx.beginPath(); ctx.arc(d.x, d.y, d.r * 0.4, 0, 2 * Math.PI); ctx.fillStyle = "rgba(255,255,255,0.92)"; ctx.fill();
      ctx.globalAlpha = 1;
    };

    const frame = () => {
      const cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.3;
      if (!reduced) t += 1;
      const groups = groupSources(dataRef.current.sources);
      const n = Math.max(groups.length, 1);
      const seen = new Set<string>(["core"]); links = [];

      const core = ensure("core", { kind: "core", color: "#FF8A4C", r: 12, label: "ATHENA", sub: dataRef.current.topic.slice(0, 80) });
      core.tx = cx; core.ty = cy;

      groups.forEach(([key, srcs], i) => {
        const ang = -Math.PI / 2 + (2 * Math.PI * i) / n;            // FIXED angle — no orbital spin
        const hx = cx + Math.cos(ang) * R, hy = cy + Math.sin(ang) * R;
        const color = ENGINE_COLORS[key] || FALLBACK[i % FALLBACK.length];
        const hid = "engine:" + key;
        const hub = ensure(hid, { kind: "agent", color, r: 7, label: key, sub: `${srcs.length} source${srcs.length === 1 ? "" : "s"}` });
        hub.tx = hx; hub.ty = hy; hub.color = color; hub.sub = `${srcs.length} source${srcs.length === 1 ? "" : "s"}`; seen.add(hid);
        links.push({ from: "core", to: hid, color });            // ATHENA -> search engine (straight)
        // sources fan OUTWARD from the engine — static positions, straight links (no spinning)
        const ring = 24 + Math.min(srcs.length, 18) * 1.5;
        const arc = Math.min(Math.PI * 0.85, 0.4 + srcs.length * 0.13);
        srcs.forEach((s, j) => {
          const sa = ang + (srcs.length > 1 ? (j / (srcs.length - 1) - 0.5) * arc : 0);
          const col = TYPE_COLORS[s.source_type] || "#94A3B8";
          const sd = ensure(s.url, { kind: "source", color: col, r: 2.6, href: s.url, label: s.title || s.url, sub: `${s.source_type} · ${s.url}` });
          sd.tx = hx + Math.cos(sa) * ring; sd.ty = hy + Math.sin(sa) * ring; sd.color = col; seen.add(s.url);
          links.push({ from: hid, to: s.url, color: col });      // engine -> source (straight)
        });
      });

      dots.forEach((d) => { d.x += (d.tx - d.x) * 0.09; d.y += (d.ty - d.y) * 0.09; d.a += ((seen.has(d.id) ? 1 : 0) - d.a) * 0.08; });
      for (const [id, d] of [...dots]) if (!seen.has(id) && d.a < 0.02) dots.delete(id);

      // ── draw (device clear, then world transform for pan/zoom) ──
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
      const v = viewRef.current; ctx.setTransform(dpr * v.scale, 0, 0, dpr * v.scale, v.ox * dpr, v.oy * dpr);

      // links + flowing particles (data passing into each section, one by one)
      links.forEach((ln, k) => {
        const a = dots.get(ln.from), b = dots.get(ln.to); if (!a || !b) return;
        ctx.strokeStyle = ln.color + "1f"; ctx.lineWidth = 0.7 / v.scale;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        if (!reduced) {
          const frac = ((t * 0.012) + (k % 7) / 7) % 1;       // travelling pulse, de-synced per link
          const px = a.x + (b.x - a.x) * frac, py = a.y + (b.y - a.y) * frac;
          const al = Math.min(a.a, b.a) * (1 - Math.abs(frac - 0.5) * 1.1);
          ctx.globalAlpha = Math.max(0, al); ctx.fillStyle = ln.color;
          ctx.beginPath(); ctx.arc(px, py, 1.7 / v.scale, 0, 2 * Math.PI); ctx.fill(); ctx.globalAlpha = 1;
        }
      });

      dots.forEach((d) => { if (d.kind === "source") drawDot(d, 8); });
      dots.forEach((d) => {
        if (d.kind !== "agent") return;
        drawDot(d, 16);
        ctx.globalAlpha = Math.max(0, Math.min(1, d.a)) * 0.4; ctx.strokeStyle = d.color; ctx.lineWidth = 1 / v.scale;
        ctx.beginPath(); ctx.arc(d.x, d.y, d.r + 5, 0, 2 * Math.PI); ctx.stroke(); ctx.globalAlpha = 1;
      });
      core.r = 12 * (reduced ? 1 : 1 + Math.sin(t * 0.045) * 0.12);
      drawDot(core, 30);
      ctx.globalAlpha = Math.max(0, Math.min(1, core.a));
      ctx.fillStyle = "rgba(236,235,232,0.9)"; ctx.font = "600 11px ui-monospace, monospace"; ctx.textAlign = "center";
      ctx.fillText("ATHENA", core.x, core.y + 27); ctx.textAlign = "start"; ctx.globalAlpha = 1;

      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf); ro.disconnect();
      canvas.removeEventListener("wheel", onWheel); canvas.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp); canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("mouseleave", onLeave); canvas.removeEventListener("click", onClick);
    };
  }, []);

  const stage = stageIndex(status);
  const engines = Math.min(8, new Set(sources.map(groupKey)).size);

  return (
    <div ref={wrapRef} className="glass graph-stage" data-testid="research-graph"
      style={{ minHeight: 460, height: "100%", overflow: "hidden", position: "relative" }}>
      <div style={{ position: "absolute", top: 12, left: 12, right: 64, zIndex: 2, display: "flex", gap: 6, flexWrap: "wrap", pointerEvents: "none" }}>
        {STAGES.map((st, i) => (
          <span key={st} style={{
            fontSize: 10.5, fontWeight: 700, padding: "3px 9px", borderRadius: 999, border: "1px solid",
            borderColor: i === stage ? "var(--accent)" : "rgba(148,163,184,0.25)",
            color: i === stage ? "var(--accent)" : "rgba(148,163,184,0.7)",
            background: i === stage ? "var(--accent-soft)" : "transparent", opacity: i <= stage ? 1 : 0.5,
          }}>{i + 1}. {st}</span>
        ))}
      </div>
      <button type="button" aria-label="fit to view"
        onClick={() => { viewRef.current = { scale: 1, ox: 0, oy: 0 }; }}
        style={{
          position: "absolute", top: 10, right: 10, zIndex: 3, cursor: "pointer",
          fontSize: 11, fontWeight: 700, padding: "5px 11px", borderRadius: 8,
          border: "1px solid rgba(148,163,184,0.3)", background: "rgba(20,20,24,0.55)", color: "rgba(236,235,232,0.9)",
        }}>⤢ Fit</button>
      <canvas ref={canvasRef} style={{ display: "block", width: "100%", height: "100%", cursor: "grab", touchAction: "none" }} />
      <div ref={tipRef} style={{
        display: "none", position: "absolute", zIndex: 4, pointerEvents: "none", maxWidth: 280,
        fontSize: 11.5, lineHeight: 1.35, padding: "7px 10px", borderRadius: 8, wordBreak: "break-word",
        background: "rgba(15,17,21,0.92)", color: "#ECEBE8", border: "1px solid rgba(148,163,184,0.25)",
      }} />
      <div style={{ position: "absolute", bottom: 10, left: 14, zIndex: 2, pointerEvents: "none",
        fontSize: 11, color: "rgba(148,163,184,0.65)", fontFamily: "var(--font-mono, monospace)" }}>
        {engines} engine{engines === 1 ? "" : "s"} · {sources.length} source{sources.length === 1 ? "" : "s"} · drag to pan · scroll to zoom
      </div>
    </div>
  );
}
