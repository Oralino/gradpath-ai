// Applies the saved light/dark choice before first paint, so a light-mode visitor never sees a
// dark flash. Loaded by app/layout.tsx as a static same-origin file (no inline script, so a later
// Content-Security-Policy can stay strict). Dark is the default; only "light" changes anything.
try {
  if (window.localStorage.getItem("gradpath-theme") === "light") {
    document.documentElement.dataset.theme = "light";
  }
} catch {
  // Storage blocked (private mode, policy): keep the dark default.
}
