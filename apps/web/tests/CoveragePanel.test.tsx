import { render, screen } from "@testing-library/react";
import { CoveragePanel } from "@/components/research/CoveragePanel";

test("renders per-sub-question coverage and entity chips", () => {
  render(<CoveragePanel
    coverage={{
      overall: 0.5,
      cells: [
        { question: "What is MCP?", validated: 2, relevant: 3, best_relevance: 0.9, score: 0.8 },
        { question: "Thin angle", validated: 0, relevant: 1, best_relevance: 0.3, score: 0.2 },
      ],
      entities: [
        { entity: "LangGraph", hits: 2, covered: true },
        { entity: "CrewAI", hits: 0, covered: false },
      ],
    }}
    entail={{ engine: "entailment", supported: 5, refuted: 1, nei: 0, conflicts: 1 }}
    urlHealth={{ total: 6, live: 6, dead: 0, unreachable: 0 }}
  />);
  expect(screen.getByText("What is MCP?")).toBeInTheDocument();
  expect(screen.getByText("50% covered")).toBeInTheDocument();
  expect(screen.getByText("✓ LangGraph")).toBeInTheDocument();
  expect(screen.getByText("○ CrewAI")).toBeInTheDocument();
  expect(screen.getByText(/6\/6/)).toBeInTheDocument();   // links live
});
