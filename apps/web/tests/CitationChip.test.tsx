import { render, screen, fireEvent } from "@testing-library/react";
import { CitationChip } from "@/components/report/CitationChip";

test("clicking a citation chip reveals its source excerpt", () => {
  render(<CitationChip n={1} citation={{ n: 1, url: "https://a.com", title: "Source A", excerpt: "the supporting text" }} />);
  fireEvent.click(screen.getByLabelText("citation 1"));
  expect(screen.getByText(/the supporting text/)).toBeInTheDocument();
});
