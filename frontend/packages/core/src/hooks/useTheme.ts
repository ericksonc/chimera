import { create } from "zustand";

export type Theme = "auto" | "light" | "dark";

interface ThemeState {
  theme: Theme;
  isDark: boolean;
  setTheme: (theme: Theme) => void;
  setIsDark: (isDark: boolean) => void;
}

export const useTheme = create<ThemeState>((set) => ({
  theme: "auto",
  isDark: false,
  setTheme: (theme) => set({ theme }),
  setIsDark: (isDark) => set({ isDark }),
}));
