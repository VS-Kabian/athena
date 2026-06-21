import { renderHook, act, waitFor } from "@testing-library/react";
import { useResearchStream } from "@/lib/sse";

class MockES {
  listeners: Record<string, (e: { data: string }) => void> = {};
  static last: MockES;
  url: string;
  constructor(url: string) { this.url = url; MockES.last = this; }
  addEventListener(t: string, fn: (e: { data: string }) => void) { this.listeners[t] = fn; }
  close() {}
  emit(t: string, data: unknown) { this.listeners[t]?.({ data: JSON.stringify(data) }); }
}

test("accumulates stream state", async () => {
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run1"));
  act(() => MockES.last.emit("round_start", { round: 1, questions: ["q"] }));
  act(() => MockES.last.emit("source", { url: "https://a.com", title: "A", provider: "ddg", source_type: "web", round: 1, providers: ["ddg"], subquestion: "q" }));
  act(() => MockES.last.emit("progress", { round: 1, discovered: 1 }));
  act(() => MockES.last.emit("done", { report_ready: true }));
  await waitFor(() => expect(result.current.done).toBe(true));
  expect(result.current.round).toBe(1);
  expect(result.current.discovered).toBe(1);
  expect(result.current.sources.length).toBe(1);
});

test("failed event sets phase=failed and captures the error message", async () => {
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run6"));
  act(() => MockES.last.emit("failed", { message: "Invalid API key" }));
  await waitFor(() => expect(result.current.phase).toBe("failed"));
  expect(result.current.error).toContain("Invalid API key");
});

test("cancelled event sets phase=cancelled", async () => {
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run7"));
  act(() => MockES.last.emit("cancelled", {}));
  await waitFor(() => expect(result.current.phase).toBe("cancelled"));
});

test("captures the verify event", async () => {
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run4"));
  act(() => MockES.last.emit("verify", { contested: 2 }));
  await waitFor(() => expect(result.current.verify?.contested).toBe(2));
});

test("times out the stream after prolonged silence", async () => {
  vi.useFakeTimers();
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run-timeout"));
  act(() => MockES.last.emit("round_start", { round: 1, questions: [] }));
  expect(result.current.phase).toBe("running");
  act(() => { vi.advanceTimersByTime(125_000); });         // backend goes silent past the watchdog window
  expect(result.current.phase).toBe("failed");
  expect(result.current.done).toBe(true);
  expect(result.current.error).toMatch(/stopped responding|timed out/i);
  vi.useRealTimers();
});

test("ongoing activity keeps the stream alive (watchdog resets per event)", async () => {
  vi.useFakeTimers();
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run-active"));
  act(() => { vi.advanceTimersByTime(80_000); MockES.last.emit("progress", { round: 1, discovered: 3 }); });
  act(() => { vi.advanceTimersByTime(80_000); MockES.last.emit("progress", { round: 1, discovered: 5 }); });
  expect(result.current.phase).toBe("running");            // never crossed the watchdog window
  expect(result.current.discovered).toBe(5);
  vi.useRealTimers();
});

test("heartbeat events keep a silent run alive (long synthesis on a reasoning model)", async () => {
  vi.useFakeTimers();
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run-hb"));
  act(() => { vi.advanceTimersByTime(100_000); MockES.last.emit("heartbeat", {}); });
  act(() => { vi.advanceTimersByTime(100_000); MockES.last.emit("heartbeat", {}); });
  expect(result.current.phase).toBe("running");            // heartbeats re-arm the watchdog past 120s
  vi.useRealTimers();
});

// F-024: the backend emits `reasoning_delta` (and `quality.consensus`) — both must be captured,
// not silently dropped.
test("accumulates reasoning_delta into the reasoning trace", async () => {
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run-reasoning"));
  act(() => MockES.last.emit("reasoning_delta", { text: "thinking " }));
  act(() => MockES.last.emit("reasoning_delta", { text: "harder" }));
  await waitFor(() => expect(result.current.reasoning).toBe("thinking harder"));
});

test("surfaces quality.consensus from the quality event", async () => {
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run-consensus"));
  act(() => MockES.last.emit("quality", { score: 80, breakdown: {}, hallucination_risk: 0.1, consensus: 0.75 }));
  await waitFor(() => expect(result.current.quality?.consensus).toBe(0.75));
});

test("captures deep-mode reflect and memory events", async () => {
  // @ts-expect-error test stub
  global.EventSource = MockES;
  const { result } = renderHook(() => useResearchStream("run2"));
  act(() => MockES.last.emit("memory", { related: [{ topic: "prior topic", similarity: 0.82 }] }));
  act(() => MockES.last.emit("reflect", { round: 1, action: "drill", reason: "gap in benchmarks" }));
  act(() => MockES.last.emit("reflect", { round: 2, action: "stop", reason: "well covered" }));
  await waitFor(() => expect(result.current.reflections.length).toBe(2));
  expect(result.current.related[0].topic).toBe("prior topic");
  expect(result.current.reflections[1].action).toBe("stop");
});
