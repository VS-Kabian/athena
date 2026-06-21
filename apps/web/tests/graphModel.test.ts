import { buildGraph } from "@/lib/graphModel";
import type { SourceEvent } from "@/lib/types";

const s = (url: string, type: string, round = 1, provider = "ddg"): SourceEvent =>
  ({ url, title: url, provider, source_type: type, round, providers: [provider], subquestion: "q" });

test("adds topic + provider + source nodes and links", () => {
  const g = buildGraph("AI", [s("https://a.com", "web"), s("https://b.com", "github", 2)]);
  const ids = g.nodes.map((n) => n.id);
  expect(ids).toContain("topic:AI");
  expect(ids).toContain("provider:ddg");
  expect(ids).toContain("https://a.com");
  expect(g.links.some((l) => l.source === "provider:ddg" && l.target === "https://a.com")).toBe(true);
  expect(g.nodes.find((n) => n.id === "https://b.com")?.type).toBe("github");
});

test("dedupes repeated source urls", () => {
  const g = buildGraph("AI", [s("https://a.com", "web"), s("https://a.com", "web")]);
  expect(g.nodes.filter((n) => n.id === "https://a.com").length).toBe(1);
});

// F-025: the source->provider link must target a provider node that was actually created from
// `s.providers`. When `s.provider` is absent from `s.providers`, the old code linked to a
// non-existent `provider:${s.provider}` node (orphan link). Every link endpoint must resolve.
test("source links never reference a missing provider node", () => {
  const src: SourceEvent = {
    url: "https://x.com", title: "X", provider: "x", source_type: "web",
    round: 1, providers: ["y"], subquestion: "q",   // provider 'x' is NOT in providers
  };
  const g = buildGraph("AI", [src]);
  const ids = new Set(g.nodes.map((n) => n.id));
  expect(ids.has("provider:x")).toBe(false);   // no node was created for 'x'
  for (const l of g.links) {
    expect(ids.has(l.source)).toBe(true);
    expect(ids.has(l.target)).toBe(true);
  }
});
