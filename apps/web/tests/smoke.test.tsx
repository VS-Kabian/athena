import { render, screen } from "@testing-library/react";

function Hello() {
  return <h1>ATHENA</h1>;
}

test("renders", () => {
  render(<Hello />);
  expect(screen.getByText("ATHENA")).toBeInTheDocument();
});
