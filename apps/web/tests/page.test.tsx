import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Stub the heavy child components so the page can render in jsdom without their internals.
vi.mock("@/components/providers/ModelPicker", () => ({
  ModelPicker: ({ onChange, disabled }: any) => (
    <button aria-label="model-picker" disabled={disabled}
      onClick={() => onChange({ provider: "deepseek", model: "deepseek-chat" })}>pick model</button>
  ),
}));
vi.mock("@/components/providers/SearchPicker", () => ({
  SearchPicker: ({ disabled }: any) => <div aria-label="search-picker" data-disabled={!!disabled} />,
}));
vi.mock("@/components/research/RoundsSlider", () => ({
  RoundsSlider: ({ disabled }: any) => <input aria-label="rounds-slider" type="range" disabled={disabled} readOnly />,
}));
vi.mock("@/components/research/StartCancel", () => ({
  StartCancel: ({ canStart, running, onStart, onCancel }: any) =>
    running
      ? <button aria-label="cancel" onClick={onCancel}>Cancel</button>
      : <button aria-label="start" disabled={!canStart} onClick={onStart}>Start</button>,
}));
vi.mock("@/components/research/StatusPanel", () => ({ StatusPanel: () => <div /> }));
vi.mock("@/components/research/ResearchGraph", () => ({ ResearchGraph: () => <div /> }));
vi.mock("@/components/report/ReportView", () => ({ ReportView: () => <div /> }));
vi.mock("@/components/report/QualityBreakdown", () => ({ QualityBreakdown: () => <div /> }));
vi.mock("@/components/report/SourceList", () => ({ SourceList: () => <div /> }));
vi.mock("@/components/report/TrustPanel", () => ({ TrustPanel: () => <div /> }));
vi.mock("@/components/report/DownloadBar", () => ({ DownloadBar: () => <div /> }));

// Controllable stream state for the page.
let streamState: any;
vi.mock("@/lib/sse", () => ({ useResearchStream: () => streamState }));

const startResearch = vi.fn();
vi.mock("@/lib/api", () => ({
  startResearch: (...a: any[]) => startResearch(...a),
  cancelResearch: () => Promise.resolve(),
  getRun: () => Promise.resolve({}),
  getPlan: () => Promise.resolve({ sub_questions: [] }),
}));

import Home from "@/app/page";

beforeEach(() => {
  startResearch.mockReset();
  streamState = {
    status: "idle", round: 0, discovered: 0, validated: 0, sources: [], done: false,
    quality: null, reflections: [], related: [], verify: null, phase: "running",
    error: null, draft: "", reasoning: "", usage: null,
  };
});

// F-023: a legitimate 0-token usage must still render the usage line (no truthiness short-circuit).
test("usage line renders for a 0-token run", async () => {
  startResearch.mockResolvedValue({ run_id: "r1" });
  streamState.usage = { total_tokens: 0 };
  render(<Home />);
  // give the page a run id + topic + model, then start so runId is set
  fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "MCP" } });
  fireEvent.click(screen.getAllByLabelText("model-picker")[0]);
  fireEvent.click(screen.getByLabelText("start"));
  await waitFor(() => expect(screen.getByText(/tokens/)).toBeInTheDocument());
  expect(screen.getByText(/^0 tokens/)).toBeInTheDocument();
});

// F-027: while a run is in flight, the topic and pickers are disabled (no mid-run edits).
test("form inputs are disabled while running", async () => {
  startResearch.mockResolvedValue({ run_id: "r2" });
  render(<Home />);
  fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "MCP" } });
  fireEvent.click(screen.getAllByLabelText("model-picker")[0]);
  fireEvent.click(screen.getByLabelText("start"));
  await waitFor(() => expect(screen.getByLabelText("cancel")).toBeInTheDocument()); // running
  expect((screen.getByLabelText(/topic/i) as HTMLTextAreaElement).disabled).toBe(true);
  expect((screen.getByLabelText("rounds-slider") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText("report type") as HTMLSelectElement).disabled).toBe(true);
});

// F-027: a failed run shows "Start again" (not a misleading silent "Retry"). With done=true the
// stream is terminal (running=false) the moment a run id is assigned, so the failed branch renders.
test("failed run shows a Start again button", async () => {
  startResearch.mockResolvedValue({ run_id: "r3" });
  streamState.phase = "failed";
  streamState.done = true;
  streamState.error = "boom";
  render(<Home />);
  fireEvent.change(screen.getByLabelText(/topic/i), { target: { value: "MCP" } });
  fireEvent.click(screen.getAllByLabelText("model-picker")[0]);
  fireEvent.click(screen.getByLabelText("start"));
  await waitFor(() => expect(screen.getByText("Start again")).toBeInTheDocument());
  expect(screen.queryByText(/^Retry$/)).not.toBeInTheDocument();
});
