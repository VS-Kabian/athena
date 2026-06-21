// Guard untrusted URLs bound to anchor hrefs: only allow absolute http(s) URLs through.
// Anything else (javascript:, data:, protocol-relative //evil.com, relative paths, invalid) -> undefined.
export function safeHref(u?: string): string | undefined {
  if (!u) return undefined;
  try {
    // Parse against a base so relative inputs don't throw; reject anything whose resolved
    // protocol isn't http(s). Relative/protocol-relative inputs resolve to the dummy base
    // and won't match the original string, so they fall through to undefined.
    const parsed = new URL(u, "http://x");
    if (!/^https?:$/i.test(parsed.protocol)) return undefined;
    // Require the input itself to be an absolute http(s) URL (not relative/protocol-relative
    // that merely resolved against the dummy base).
    if (!/^https?:\/\//i.test(u)) return undefined;
    return u;
  } catch {
    return undefined;
  }
}
