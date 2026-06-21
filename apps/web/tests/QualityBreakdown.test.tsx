import { render, screen } from "@testing-library/react";
import { QualityBreakdown } from "@/components/report/QualityBreakdown";

test("renders the five quality dimensions", () => {
  render(<QualityBreakdown breakdown={{ coverage: 18, validation: 10, grounding: 30, relevance: 12, depth: 13, hallucination_risk: 0.0 }} />);
  expect(screen.getByText("Coverage")).toBeInTheDocument();
  expect(screen.getByText("Grounding")).toBeInTheDocument();
  expect(screen.getByText("18/18")).toBeInTheDocument();
});
