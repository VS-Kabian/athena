import type { SourceEvent } from "./types";

export type GNode = { id: string; label: string; kind: "topic" | "provider" | "source"; type?: string; round?: number };
export type GLink = { source: string; target: string };
export type Graph = { nodes: GNode[]; links: GLink[] };

export function buildGraph(topic: string, sources: SourceEvent[]): Graph {
  const nodes = new Map<string, GNode>();
  const links: GLink[] = [];
  const topicId = `topic:${topic}`;
  nodes.set(topicId, { id: topicId, label: topic, kind: "topic" });
  for (const s of sources) {
    const provs = s.providers && s.providers.length ? s.providers : [s.provider];
    for (const p of provs) {
      const pid = `provider:${p}`;
      if (!nodes.has(pid)) {
        nodes.set(pid, { id: pid, label: p, kind: "provider" });
        links.push({ source: topicId, target: pid });
      }
    }
    if (!nodes.has(s.url)) {
      nodes.set(s.url, { id: s.url, label: s.title, kind: "source", type: s.source_type, round: s.round });
      // link to a provider node we actually created (provs[0]); `s.provider` may be absent from
      // `s.providers`, which would point this link at a non-existent node id (orphan link).
      links.push({ source: `provider:${provs[0]}`, target: s.url });
    }
  }
  return { nodes: [...nodes.values()], links };
}
