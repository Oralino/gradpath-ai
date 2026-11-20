import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Next } from "next/font/google";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

// Self-hosted at build time by next/font: no request to Google from the visitor's browser.
// next/font has no metric overrides for this family, so it can't build a size-matched fallback;
// say so explicitly and fall back to the system stack.
const atkinson = Atkinson_Hyperlegible_Next({
  variable: "--font-atkinson",
  subsets: ["latin"],
  display: "swap",
  adjustFontFallback: false,
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
});

export const metadata: Metadata = {
  title: "GradPath",
  description:
    "Preparation plans and cited answers for new-grad backend roles, from a curated knowledge base.",
};

// Root layout: theme script, skip link, header, main, footer (DESIGN.md, Screens and
// Accessibility). suppressHydrationWarning on <html> only: theme-init.js may set data-theme
// before React hydrates, which is expected.
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${atkinson.variable} motion-safe:scroll-smooth`} suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts -- must run before first paint */}
        <script src="/theme-init.js" />
      </head>
      <body className="flex min-h-screen flex-col bg-paper font-sans text-body text-ink antialiased">
        <a
          href="#main"
          className="sr-only rounded-md bg-surface px-3 py-2 text-label text-ink focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-20"
        >
          Skip to main content
        </a>
        <SiteHeader />
        <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-12 sm:px-6 lg:px-8">
          {children}
        </main>
        <footer className="border-t border-rule">
          <p className="mx-auto w-full max-w-5xl px-4 py-6 text-meta text-ink-muted sm:px-6 lg:px-8">
            Preparation support only, not a hiring prediction · Answers can be wrong: check the
            sources.
          </p>
        </footer>
      </body>
    </html>
  );
}
