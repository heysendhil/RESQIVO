// Light and dark themes. Light is the default; the choice is remembered in
// this browser only. The theme is a data-theme attribute on <html>, set by an
// inline script before the first paint (app/layout.tsx), so a saved dark
// theme never flashes light.

export type Theme = "light" | "dark";

export const THEME_KEY = "resqivo.theme";

/** Runs before React loads; keep it small and self-contained. */
export const THEME_SCRIPT = `try{if(localStorage.getItem("${THEME_KEY}")==="dark")document.documentElement.dataset.theme="dark"}catch(e){}`;

export function currentTheme(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  if (theme === "dark") document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage can be unavailable; the theme then lasts for this page only.
  }
}
