import { render, screen } from "@testing-library/react";
import { ClaimsTable } from "@/components/report/ClaimsTable";

test("renders a verdict badge per claim with a count", () => {
  render(<ClaimsTable claims={[
    { text: "LangGraph is graph-based", verdict: "supported", confidence: 0.9, conflict: false },
    { text: "CrewAI hit 900 QPS", verdict: "refuted", confidence: 0.4, conflict: true },
  ]} />);
  expect(screen.getByText("Claim verdicts (2)")).toBeInTheDocument();
  expect(screen.getByText("Supported")).toBeInTheDocument();
  expect(screen.getByText("Refuted")).toBeInTheDocument();
  expect(screen.getByText("Conflict")).toBeInTheDocument();        // cross-source conflict badge
  expect(screen.getByText("CrewAI hit 900 QPS")).toBeInTheDocument();
});

test("renders nothing when there are no claims", () => {
  const { container } = render(<ClaimsTable claims={[]} />);
  expect(container).toBeEmptyDOMElement();
});

test("shows a percentage for claims that carry a confidence", () => {
  render(<ClaimsTable claims={[
    { text: "A grounded claim", verdict: "supported", confidence: 0.82, conflict: false },
  ]} />);
  expect(screen.getByText("82%")).toBeInTheDocument();
});
