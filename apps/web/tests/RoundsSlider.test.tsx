import { render, screen, fireEvent } from "@testing-library/react";
import { RoundsSlider } from "@/components/research/RoundsSlider";

test("emits selected round count", () => {
  let val = 0;
  render(<RoundsSlider onChange={(n) => (val = n)} />);
  fireEvent.change(screen.getByLabelText(/research rounds/i), { target: { value: "4" } });
  expect(val).toBe(4);
});
