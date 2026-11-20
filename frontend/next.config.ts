import type { NextConfig } from "next";

// Where the FastAPI backend runs. The browser only ever calls same-origin `/api/...`; Next
// forwards it here, so the backend needs no CORS rule and its address never reaches the client.
const apiUrl = process.env.GRADPATH_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  poweredByHeader: false,
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
