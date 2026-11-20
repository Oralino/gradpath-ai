import type { NextConfig } from "next";

// Where the FastAPI backend runs. The browser only ever calls same-origin `/api/...`; Next
// forwards it here, so the backend needs no CORS rule and its address never reaches the client.
const apiUrl = process.env.GRADPATH_API_URL ?? "http://127.0.0.1:8000";

// How long the /api proxy waits for the backend. Next's default is 30 s
// (next/dist/server/lib/router-utils/proxy-request.js), which cut off RAG answers waiting on
// Voyage's rate limit and would cut off every workflow run (T-013). It must stay above the
// backend's run budget (WORKFLOW_TIME_BUDGET_S, default 300 s) so the backend always gets to
// return its own "stopped early" result; DESIGN.md's client cut-off is 320 s.
const PROXY_TIMEOUT_MS = 330_000;

const nextConfig: NextConfig = {
  poweredByHeader: false,
  experimental: { proxyTimeout: PROXY_TIMEOUT_MS },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
