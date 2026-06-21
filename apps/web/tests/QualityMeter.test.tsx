import { render, screen } from "@testing-library/react";
import { QualityMeter } from "@/components/research/QualityMeter";

test("renders score and risk", () => {
  render(<QualityMeter score={82} risk={0.05} />);
  expect(screen.getByText("82")).toBeInTheDocument();
  expect(screen.getByText("5%")).toBeInTheDocument();
  expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "82");
});
