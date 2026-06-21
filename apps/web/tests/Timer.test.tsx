import { render, screen, act } from "@testing-library/react";
import { Timer } from "@/components/research/Timer";

test("counts up while running and freezes when stopped", () => {
  vi.useFakeTimers();
  const { rerender } = render(<Timer running={true} />);
  act(() => { vi.advanceTimersByTime(3000); });
  expect(screen.getByTestId("timer").textContent).toBe("00:03");
  rerender(<Timer running={false} />);
  act(() => { vi.advanceTimersByTime(5000); });
  expect(screen.getByTestId("timer").textContent).toBe("00:03");
  vi.useRealTimers();
});
