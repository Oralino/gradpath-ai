"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeToggle";

// The header on every page (DESIGN.md, Screens): wordmark, four nav links, theme toggle. A client
// component only because it needs the current path for aria-current. No hamburger menu: at phone
// width the links wrap to a second row.
const NAV = [
  { href: "/", label: "Ask" },
  { href: "/job", label: "Analyse a job" },
  { href: "/plan", label: "Plan" },
  { href: "/profile", label: "Profile" },
] as const;

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-10 border-b border-rule bg-paper">
      <div className="mx-auto flex min-h-14 w-full max-w-5xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-2 sm:px-6 lg:px-8">
        <Link href="/" className="text-label text-ink no-underline">
          GradPath
        </Link>
        <nav aria-label="Main" className="order-3 flex w-full flex-wrap gap-x-6 gap-y-1 text-label sm:order-none sm:w-auto sm:flex-1">
          {NAV.map((item) => {
            const current = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={
                  current
                    ? "py-1 text-ink underline decoration-2 underline-offset-[6px]"
                    : "py-1 text-ink-muted no-underline transition-colors duration-150 hover:text-ink"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto sm:ml-0">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
