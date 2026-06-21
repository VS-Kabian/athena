import { render, screen } from "@testing-library/react";
import { StatusPanel } from "@/components/research/StatusPanel";

test("renders all status fields", () => {
  render(<StatusPanel status="Round 1" round={1} roundsTotal={2} discovered={5} validated={3}
                       model="gemini-2.5-flash" providers={["ddg", "searxng"]} running={true} />);
  expect(screen.getByText("Round 1")).toBeInTheDocument();
  expect(screen.getByText("1 / 2")).toBeInTheDocument();
  expect(screen.getByText("5")).toBeInTheDocument();
  expect(screen.getByText("gemini-2.5-flash")).toBeInTheDocument();
  expect(screen.getByText("ddg, searxng")).toBeInTheDocument();
});

test("shows quality meter when provided", () => {
  render(<StatusPanel status="Done" round={2} roundsTotal={2} discovered={9} validated={5}
                       model="gemini-2.5-flash" providers={["ddg"]} running={false}
                       quality={{ score: 77, risk: 0.08 }} />);
  expect(screen.getByText("77")).toBeInTheDocument();
  expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "77");
});
