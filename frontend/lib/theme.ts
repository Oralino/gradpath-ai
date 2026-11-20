// Light/dark theme choice (DESIGN.md, Theme toggle). Dark is the default. The choice lives in
// localStorage under the same key that public/theme-init.js reads before first paint; every
// storage access is guarded because storage can be blocked.

export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "gradpath-theme";

/** The theme currently applied to <html>, which theme-init.js set from storage. */
export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

/** Apply a theme to <html> and remember it; a failed save still applies it for this visit. */
export function applyTheme(theme: Theme): void {
  if (theme === "light") {
    document.documentElement.dataset.theme = "light";
  } else {
    delete document.documentElement.dataset.theme;
  }
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage blocked: the choice lasts until the page is reloaded.
  }
}
