import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const { getKeys, putKey, deleteKey, testKey } = vi.hoisted(() => ({
  getKeys: vi.fn(), putKey: vi.fn(), deleteKey: vi.fn(), testKey: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ getKeys, putKey, deleteKey, testKey }));

import { KeyVault } from "@/components/settings/KeyVault";

beforeEach(() => { getKeys.mockReset(); putKey.mockReset(); deleteKey.mockReset(); testKey.mockReset(); });

test("shows error feedback when save fails (stale/offline API)", async () => {
  getKeys.mockResolvedValue([]);
  putKey.mockResolvedValue({ ok: false, status: 404 });
  render(<KeyVault />);
  const input = await screen.findByLabelText("groq input");
  fireEvent.change(input, { target: { value: "sk-abc123" } });
  fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);
  expect(await screen.findByText(/couldn't save/i)).toBeInTheDocument();
});

test("confirms saved on success", async () => {
  getKeys.mockResolvedValueOnce([]).mockResolvedValue([
    { provider: "groq", set: true, masked: "sk-••••1234" },
  ]);
  putKey.mockResolvedValue({ ok: true });
  render(<KeyVault />);
  const input = await screen.findByLabelText("groq input");
  fireEvent.change(input, { target: { value: "sk-abc123" } });
  fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);
  await waitFor(() => expect(screen.getByText(/saved ·/i)).toBeInTheDocument());
});

test("shows a connection banner when the key store is unreachable", async () => {
  getKeys.mockRejectedValue(new Error("offline"));
  render(<KeyVault />);
  expect(await screen.findByText(/can't reach the api/i)).toBeInTheDocument();
});

test("Test button shows validation result", async () => {
  getKeys.mockResolvedValue([{ provider: "groq", set: true, masked: "gsk•••1234" }]);
  testKey.mockResolvedValue({ ok: true, message: "Key valid (llama-3.3-70b)." });
  render(<KeyVault />);
  const btn = await screen.findByRole("button", { name: "Test" });
  fireEvent.click(btn);
  expect(await screen.findByText(/key valid/i)).toBeInTheDocument();
});
