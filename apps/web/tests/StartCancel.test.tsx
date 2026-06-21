import { render, screen, fireEvent } from "@testing-library/react";
import { StartCancel } from "@/components/research/StartCancel";

test("start triggers onStart; cancel disabled until running", () => {
  let started = false, cancelled = false;
  const { rerender } = render(
    <StartCancel canStart running={false} onStart={() => (started = true)} onCancel={() => (cancelled = true)} />
  );
  fireEvent.click(screen.getByText("Start Research"));
  expect(started).toBe(true);
  expect(screen.getByText("Cancel Research")).toBeDisabled();
  rerender(<StartCancel canStart running onStart={() => {}} onCancel={() => (cancelled = true)} />);
  fireEvent.click(screen.getByText("Cancel Research"));
  expect(cancelled).toBe(true);
});
