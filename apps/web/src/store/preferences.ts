import { useEffect, useState } from "react";
import { create } from "zustand";

export type ThemePreference = "system" | "light" | "dark";
type StoredPreferences = { theme: ThemePreference; advanced: boolean; sidebarCollapsed: boolean };
type PreferencesState = StoredPreferences & {
  setTheme: (theme: ThemePreference) => void;
  setAdvanced: (advanced: boolean) => void;
  toggleSidebar: () => void;
};

const STORAGE_KEY = "yingzhang.ui-preferences.v1";
const DEFAULTS: StoredPreferences = { theme: "system", advanced: false, sidebarCollapsed: false };

/** Storage may be unavailable (private mode, blocked site data); preferences then last for the session. */
function readStored(): StoredPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<StoredPreferences>;
    return {
      theme: parsed.theme === "light" || parsed.theme === "dark" ? parsed.theme : "system",
      advanced: parsed.advanced === true,
      sidebarCollapsed: parsed.sidebarCollapsed === true,
    };
  } catch {
    return DEFAULTS;
  }
}

function writeStored(value: StoredPreferences) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* ignore: preference stays in memory */
  }
}

export function applyTheme(theme: ThemePreference) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

const initial = typeof window === "undefined" ? DEFAULTS : readStored();
applyTheme(initial.theme);

export const usePreferences = create<PreferencesState>((set, get) => {
  const persist = (patch: Partial<StoredPreferences>) => {
    const { theme, advanced, sidebarCollapsed } = { ...get(), ...patch };
    writeStored({ theme, advanced, sidebarCollapsed });
    set(patch);
  };
  return {
    ...initial,
    setTheme: (theme) => {
      applyTheme(theme);
      persist({ theme });
    },
    setAdvanced: (advanced) => persist({ advanced }),
    toggleSidebar: () => persist({ sidebarCollapsed: !get().sidebarCollapsed }),
  };
});

const darkQuery = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

/** The theme actually shown, resolving "system" against the OS setting. */
export function useResolvedTheme(): "light" | "dark" {
  const theme = usePreferences((state) => state.theme);
  const [systemDark, setSystemDark] = useState(() => Boolean(darkQuery()?.matches));
  useEffect(() => {
    const query = darkQuery();
    if (!query) return;
    const update = () => setSystemDark(query.matches);
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return theme === "system" ? (systemDark ? "dark" : "light") : theme;
}
