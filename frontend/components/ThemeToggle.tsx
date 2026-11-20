"use client";

import { useEffect, useState } from "react";
import { applyTheme, currentTheme, type Theme } from "@/lib/theme";

// Header button that switches light/dark (DESIGN.md, Theme toggle). It reads the theme from
// <html> after mount, not during render, because the server can't know the saved choice and a
// render-time read would cause a hydration mismatch.
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    // Sync once from what theme-init.js applied before React loaded.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(currentTheme());
  }, []);

  const isDark = theme === "dark";

  function toggle() {
    const next: Theme = isDark ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={isDark}
      className="inline-flex h-11 items-center gap-2 rounded-md border border-line bg-surface px-3 text-label text-ink transition-colors duration-150 hover:bg-sunken sm:h-9"
    >
      {isDark ? <MoonIcon /> : <SunIcon />}
      Dark mode
    </button>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
    </svg>
  );
}
