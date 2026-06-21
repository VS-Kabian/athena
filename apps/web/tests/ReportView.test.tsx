import { render, screen } from "@testing-library/react";
import { ReportView } from "@/components/report/ReportView";

test("renders markdown headings and text", () => {
  render(<ReportView markdown={"# Findings\n\nClaim about AI."} />);
  expect(screen.getByText("Findings")).toBeInTheDocument();
  expect(screen.getByText("Claim about AI.")).toBeInTheDocument();
});

test("sanitizes unsafe non-citation links in markdown", () => {
  const { container } = render(<ReportView markdown={"[Safe](https://example.com) and [Unsafe](javascript:alert(1))"} />);
  const safeLink = screen.getByText("Safe");
  expect(safeLink.getAttribute("href")).toBe("https://example.com");

  const unsafeLink = screen.getByText("Unsafe");
  // React strips undefined attributes from HTML elements, resulting in getAttribute returning null
  expect(unsafeLink.getAttribute("href")).toBeNull();
});
