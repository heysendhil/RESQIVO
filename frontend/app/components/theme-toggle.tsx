"use client";

import { useEffect, useState } from "react";

import { applyTheme, currentTheme, type Theme } from "@/lib/theme";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  // Read the theme the inline script applied, after mounting.
  useEffect(() => {
    const id = setTimeout(() => setTheme(currentTheme()), 0);
    return () => clearTimeout(id);
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={theme === "dark"}
      aria-label="Dark theme"
      onClick={() => {
        applyTheme(next);
        setTheme(next);
      }}
      className="inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-0.5 text-xs text-ink hover:border-accent/60"
    >
      <span aria-hidden="true">{theme === "dark" ? "☾" : "☀"}</span>
      {theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}
