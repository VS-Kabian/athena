import { render, screen } from "@testing-library/react";
import { ResearchGraph } from "@/components/research/ResearchGraph";
import type { SourceEvent } from "@/lib/types";

// jsdom has no 2D canvas; the component renders the shell + overlays and skips the animation.
const sources: SourceEvent[] = [
  { url: "https://a.com", title: "A", provider: "ddg", source_type: "web", round: 1, providers: ["ddg"], subquestion: "facet one" },
  { url: "https://b.com", title: "B", provider: "tavily", source_type: "docs", round: 1, providers: ["tavily"], subquestion: "facet two" },
];

test("renders the research animation shell with the stage tracker", () => {
  render(<ResearchGraph topic="AI" sources={sources} status="Synthesizing report" />);
  expect(screen.getByTestId("research-graph")).toBeInTheDocument();
  // every pipeline stage is shown, with the current one derived from status
  expect(screen.getByText("1. Plan")).toBeInTheDocument();
  expect(screen.getByText("4. Synthesize")).toBeInTheDocument();
});

test("shows the live engine + source counts (one hub per search engine)", () => {
  render(<ResearchGraph topic="AI" sources={sources} status="Round 2" />);   // ddg + tavily -> 2 engines
  expect(screen.getByText(/2 engines/)).toBeInTheDocument();
  expect(screen.getByText(/2 sources/)).toBeInTheDocument();
});
