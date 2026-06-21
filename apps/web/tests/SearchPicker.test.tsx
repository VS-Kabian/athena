import { render, screen, fireEvent } from "@testing-library/react";
import { SearchPicker } from "@/components/providers/SearchPicker";

vi.mock("@/lib/api", () => ({ getKeys: () => Promise.resolve([]) }));

test("defaults to ddg+searxng and toggling tavily adds it", () => {
  const calls: { providers: string[] }[] = [];
  render(<SearchPicker onChange={(v) => calls.push(v)} />);
  expect(calls[0].providers).toEqual(["ddg", "searxng"]);
  fireEvent.click(screen.getByLabelText("Tavily"));
  expect(calls[calls.length - 1].providers).toContain("tavily");
});
