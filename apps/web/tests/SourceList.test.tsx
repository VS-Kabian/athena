import { render, screen } from "@testing-library/react";
import { SourceList } from "@/components/report/SourceList";

test("groups sources and shows count", () => {
  render(<SourceList sources={[
    { url: "https://a.com", title: "Web A", source_type: "web", round: 1 },
    { url: "https://github.com/x/y", title: "Repo Y", source_type: "github", round: 2, validated: true },
  ]} />);
  expect(screen.getByText("Sources (2)")).toBeInTheDocument();
  expect(screen.getByText("Web A")).toBeInTheDocument();
  expect(screen.getByText("✓ Repo Y")).toBeInTheDocument();
  expect(screen.getByText("GitHub")).toBeInTheDocument();
});

test("badges a dead source link from the trust ledger url_status", () => {
  render(<SourceList
    sources={[{ url: "https://gone.com", title: "Gone", source_type: "web", round: 1 }]}
    urlStatus={{ "https://gone.com": "dead" }} />);
  expect(screen.getByText("dead link")).toBeInTheDocument();
});

test("does not render a clickable link for a dead source (P3)", () => {
  render(<SourceList
    sources={[{ url: "https://gone.example/x", title: "Gone Page", source_type: "web", round: 1 }]}
    urlStatus={{ "https://gone.example/x": "dead" }} />);
  expect(screen.getByText("Gone Page")).toBeInTheDocument();                       // still shown...
  expect(screen.queryByRole("link", { name: /Gone Page/ })).not.toBeInTheDocument();  // ...but NOT clickable
});
