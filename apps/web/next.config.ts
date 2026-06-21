import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  async headers() {
    // Derive the API origin from env so connect-src can be narrowed to exactly the backend
    // instead of a blanket `https:`. Also allow the matching ws/wss origin (SSE/websocket safety).
    const apiBase = process.env.NEXT_PUBLIC_API ?? "http://localhost:7000";
    let apiOrigin = apiBase;
    let wsOrigin = apiBase.replace(/^http/i, "ws");
    try {
      const u = new URL(apiBase);
      apiOrigin = u.origin;
      wsOrigin = `${u.protocol === "https:" ? "wss:" : "ws:"}//${u.host}`;
    } catch {}
    // React/Next.js (Turbopack) use eval() in DEV for HMR, source maps, and callstack reconstruction,
    // so 'unsafe-eval' is required for `next dev` to run. It is dropped in production (the audit
    // hardening) — React never uses eval() in prod. connect-src is likewise relaxed in dev so the
    // HMR/dev-overlay websocket isn't blocked.
    const isDev = process.env.NODE_ENV !== "production";
    const csp = [
      "default-src 'self'",
      // TODO: replace 'unsafe-inline' with a per-request nonce (needs middleware; out of scope here)
      isDev
        ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
        : "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self' data:",
      isDev
        ? `connect-src 'self' ${apiOrigin} ${wsOrigin} ws: wss:`
        : `connect-src 'self' ${apiOrigin} ${wsOrigin}`,
    ].join("; ");
    return [{ source: "/(.*)", headers: [
      { key: "Content-Security-Policy", value: csp },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    ]}];
  },
};

export default nextConfig;
