import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ModelPicker } from "@/components/providers/ModelPicker";

vi.mock("next/link", () => ({ default: ({ children, ...p }: any) => <a {...p}>{children}</a> }));

// Controllable per-provider getModels so a test can resolve provider A *after* provider B.
const deferred: Record<string, { resolve: (m: string[]) => void; promise: Promise<string[]> }> = {};
function makeDeferred(provider: string) {
  let resolve!: (m: string[]) => void;
  const promise = new Promise<string[]>((r) => { resolve = r; });
  deferred[provider] = { resolve, promise };
  return promise;
}

vi.mock("@/lib/api", () => ({
  getProviders: () => Promise.resolve([
    { id: "deepseek", label: "DeepSeek", needs_key: true },
    { id: "openai", label: "OpenAI", needs_key: true },
  ]),
  getModels: (provider: string) => makeDeferred(provider),
  getKeys: () => Promise.resolve([]),
}));

beforeEach(() => { for (const k of Object.keys(deferred)) delete deferred[k]; });

test("selecting a provider loads its models", async () => {
  render(<ModelPicker onChange={() => {}} />);
  fireEvent.change(await screen.findByLabelText(/provider/i), { target: { value: "deepseek" } });
  deferred["deepseek"].resolve(["deepseek-chat", "deepseek-reasoner"]);
  await waitFor(() => expect(screen.getByText("deepseek-reasoner")).toBeInTheDocument());
});

// F-009: switching A->B while A's getModels is still in flight must not let A's slower response
// win. After resolving B first, then A (late), the rendered models and the onChange payload must
// reflect B only — never B selected with A's models.
test("a slow provider response cannot override a faster later switch (latest-wins)", async () => {
  const onChange = vi.fn();
  render(<ModelPicker onChange={onChange} />);
  const sel = await screen.findByLabelText(/provider/i);

  fireEvent.change(sel, { target: { value: "deepseek" } });   // A: getModels(deepseek) in flight
  fireEvent.change(sel, { target: { value: "openai" } });     // B: switch before A resolves

  deferred["openai"].resolve(["gpt-x", "gpt-y"]);             // B resolves first
  await waitFor(() => expect(screen.getByText("gpt-x")).toBeInTheDocument());

  deferred["deepseek"].resolve(["deepseek-chat", "deepseek-reasoner"]);  // A resolves LATE — must be ignored

  // A's models must never appear; B's must remain.
  await waitFor(() => expect(screen.queryByText("deepseek-reasoner")).not.toBeInTheDocument());
  expect(screen.getByText("gpt-x")).toBeInTheDocument();

  // The emitted (provider, model) pair must be consistent: provider B with one of B's models.
  const last = onChange.mock.calls.at(-1)?.[0];
  expect(last).toEqual({ provider: "openai", model: "gpt-x" });
});
