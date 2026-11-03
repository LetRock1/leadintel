import { createContext, useContext } from "react";

export type ThemeChoice = "light" | "dark" | "system";

export const THEME_KEY = "xe-theme";

export interface ThemeState {
  choice: ThemeChoice;
  resolved: "light" | "dark";
  setChoice: (c: ThemeChoice) => void;
  toggle: () => void;
}

export const ThemeContext = createContext<ThemeState | null>(null);

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}

/** Sets the theme class before React starts, so the first paint already has the right colours. */
export const themeBootScript = `(()=>{try{var c=localStorage.getItem("${THEME_KEY}");var d=c==="dark"||((!c||c==="system")&&matchMedia("(prefers-color-scheme: dark)").matches);if(d)document.documentElement.classList.add("dark")}catch(e){}})()`;
