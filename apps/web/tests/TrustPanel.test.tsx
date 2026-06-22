import { render, screen } from "@testing-library/react";
import { TrustPanel, parseFlag } from "@/components/report/TrustPanel";

test("parseFlag classifies each verdict from the flagged string format", () => {
  expect(parseFlag("⚠ [verifier: corrected] The sky is blue [1].").verdict).toBe("corrected");
  expect(parseFlag("⚠ [verifier: weak] Maybe true [2].").verdict).toBe("weak");
  expect(parseFlag("⚠ single-source (uncorroborated): One blog said X [3].").verdict).toBe("single-source");
  expect(parseFlag("Unsupported bare claim [4].").verdict).toBe("unsupported");
  // strips the prefix for display
  expect(parseFlag("⚠ [verifier: corrected] Fixed sentence [1].").text).toBe("Fixed sentence [1].");
});

test("renders a color-coded badge per flagged claim with a count", () => {
  render(<TrustPanel flagged={[
    "⚠ [verifier: corrected] The sky is blue [1].",
    "⚠ single-source (uncorroborated): One blog said X [2].",
  ]} />);
  expect(screen.getByText("Corrected")).toBeInTheDocument();
  expect(screen.getByText("Single source")).toBeInTheDocument();
  expect(screen.getByText("2 flagged")).toBeInTheDocument();
});

test("shows the all-clear only when the entailment judge actually verified the claims", () => {
  render(<TrustPanel flagged={[]} trust={{ engine: "entailment", supported: 5, refuted: 0, nei: 0 }} />);
  expect(screen.getByText(/none were left unsupported/i)).toBeInTheDocument();
  expect(screen.getByText("0 flagged")).toBeInTheDocument();
});

test("does NOT show a false all-clear when no entailment verdict exists (P0-4)", () => {
  render(<TrustPanel flagged={[]} />);   // no trust ledger -> the judge did not run
  expect(screen.queryByText(/none were left unsupported/i)).not.toBeInTheDocument();
  expect(screen.getByText(/not independently verified/i)).toBeInTheDocument();
});

test("shows a reduced-assurance banner for a similarity-only (cosine) run, and no all-clear", () => {
  render(<TrustPanel flagged={[]} trust={{ engine: "embedding", supported: 3, refuted: 0, nei: 0 }} />);
  expect(screen.getByText(/reduced assurance/i)).toBeInTheDocument();
  expect(screen.queryByText(/none were left unsupported/i)).not.toBeInTheDocument();
});

test("does not show the all-clear when entailment checked zero claims", () => {
  render(<TrustPanel flagged={[]} trust={{ engine: "entailment", supported: 0, refuted: 0, nei: 0 }} />);
  expect(screen.queryByText(/none were left unsupported/i)).not.toBeInTheDocument();
  expect(screen.getByText(/not independently verified/i)).toBeInTheDocument();
});

test("parseFlag classifies the entailment, conflict, and dead-link verdicts", () => {
  expect(parseFlag("⚠ [entailment: refuted] X says the opposite [1].").verdict).toBe("refuted");
  expect(parseFlag("⚠ [entailment: not-enough-info] Loosely related [2].").verdict).toBe("nei");
  expect(parseFlag("⚠ [conflict: sources disagree] A vs B [3].").verdict).toBe("conflict");
  expect(parseFlag("⚠ [link dead] https://gone.example/x").verdict).toBe("link-dead");
});

test("renders the entailment + link-health summary from the trust ledger", () => {
  render(<TrustPanel flagged={[]} trust={{
    engine: "entailment", supported: 18, refuted: 2, nei: 1, conflicts: 1,
    url_health: { total: 24, live: 23, dead: 1, unreachable: 0 },
  }} />);
  expect(screen.getByText(/Entailment NLI/)).toBeInTheDocument();
  expect(screen.getByText("18")).toBeInTheDocument();        // supported count
  expect(screen.getByText("Source conflicts")).toBeInTheDocument();
  expect(screen.getByText("23/24")).toBeInTheDocument();     // links live
});
