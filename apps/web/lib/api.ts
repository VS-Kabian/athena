import type { Provider } from "./types";

const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:7000";

// Optional shared-secret bearer token (set once in the browser when the backend enforces auth).
// Unset on localhost -> no header -> open API, no friction.
function authHeaders(): Record<string, string> {
  if (typeof localStorage === "undefined") return {};
  const t = localStorage.getItem("athena:api_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}

// Throw on a non-2xx instead of letting an error body (e.g. {detail: "..."}) be silently parsed as
// success data — that's how a 500 used to become `{ run_id: undefined }` and a blank, frozen UI.
async function jsonOrThrow(r: Response) {
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json())?.detail ?? ""; } catch {}
    throw new Error(detail || `Request failed (${r.status})`);
  }
  return r.json();
}

export async function getProviders(): Promise<Provider[]> {
  const r = await fetch(`${BASE}/api/providers`, { headers: authHeaders() });
  return (await jsonOrThrow(r)).providers;
}
export async function getModels(provider: string, apiKey?: string): Promise<string[]> {
  // send the provider key in a header, never the URL query string (which leaks into logs/history)
  const headers = { ...authHeaders(), ...(apiKey ? { "X-Provider-Key": apiKey } : {}) };
  const r = await fetch(`${BASE}/api/providers/${provider}/models`, { headers });
  return (await jsonOrThrow(r)).models;
}
export async function getPlan(body: unknown): Promise<{ sub_questions: string[]; entities: string[] }> {
  const r = await fetch(`${BASE}/api/plan`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}
export async function startResearch(body: unknown): Promise<{ run_id: string }> {
  const r = await fetch(`${BASE}/api/research`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}
export async function cancelResearch(id: string) {
  return fetch(`${BASE}/api/research/${id}/cancel`, { method: "POST", headers: authHeaders() });
}
export async function getRun(id: string) {
  const r = await fetch(`${BASE}/api/research/${id}`, { headers: authHeaders() });
  return jsonOrThrow(r);
}
export async function getClaims(id: string): Promise<{ claims: import("./types").Claim[] }> {
  const r = await fetch(`${BASE}/api/research/${id}/claims`, { headers: authHeaders() });
  return jsonOrThrow(r);
}

export type SavedKey = { provider: string; set: boolean; masked: string };
export async function getKeys(): Promise<SavedKey[]> {
  const r = await fetch(`${BASE}/api/keys`, { headers: authHeaders() });
  return (await jsonOrThrow(r)).keys ?? [];
}
export async function putKey(provider: string, api_key: string) {
  return fetch(`${BASE}/api/keys/${provider}`, {
    method: "PUT", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ api_key }),
  });
}
export async function deleteKey(provider: string) {
  return fetch(`${BASE}/api/keys/${provider}`, { method: "DELETE", headers: authHeaders() });
}
export async function testKey(provider: string): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${BASE}/api/keys/${provider}/test`, { method: "POST", headers: authHeaders() });
  if (!r.ok) return { ok: false, message: `Test failed (${r.status})` };   // don't render an error as "valid"
  return r.json();
}

// Download a report via fetch (so the Authorization header is sent) and save the blob. A plain
// <a download> can't carry auth headers, so it would 401 once a token is configured.
export async function downloadReport(runId: string, fmt: "md" | "pdf"): Promise<void> {
  const r = await fetch(`${BASE}/api/research/${runId}/report.${fmt}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`Download failed (${r.status})`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `report-${runId}.${fmt}`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);   // let the browser buffer before revoking (FF/Safari)
}
