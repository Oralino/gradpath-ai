import { afterEach, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { THEME_STORAGE_KEY } from "@/lib/theme";

afterEach(() => {
  cleanup();
  delete document.documentElement.dataset.theme;
  window.localStorage.clear();
});

test("starts dark and switches to light and back, saving the choice", () => {
  render(<ThemeToggle />);
  const button = screen.getByRole("button", { name: "Dark mode" });
  expect(button.getAttribute("aria-pressed")).toBe("true");

  fireEvent.click(button);
  expect(document.documentElement.dataset.theme).toBe("light");
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  expect(button.getAttribute("aria-pressed")).toBe("false");

  fireEvent.click(button);
  expect(document.documentElement.dataset.theme).toBeUndefined();
  expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
});

test("reads a light theme that theme-init.js already applied", () => {
  document.documentElement.dataset.theme = "light";
  render(<ThemeToggle />);
  expect(screen.getByRole("button", { name: "Dark mode" }).getAttribute("aria-pressed")).toBe(
    "false",
  );
});
