import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Setup from the Next.js 16 testing guide (node_modules/next/dist/docs/01-app/02-guides/testing/
// vitest.md), with Vite's built-in tsconfig paths instead of a plugin. Tests never call the real
// API: fetch is mocked per test.
export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    include: ["**/*.test.{ts,tsx}"],
    setupFiles: ["./vitest.setup.ts"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
