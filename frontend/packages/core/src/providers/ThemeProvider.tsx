import { useEffect, type ReactNode } from "react";
import { useTheme, type Theme } from "../hooks/useTheme";
import { useAdapters } from "./AdapterProvider";

import { ThemeEventListener } from "@chimera/platform";

interface ThemeProviderProps {
  children: ReactNode;
  themeListener?: ThemeEventListener;
}

/**
 * Provides application-wide theme management: initializes the theme from localStorage, applies or removes the "dark" class on the document root, persists the selected theme, updates dark-mode state, and subscribes to system and platform theme changes when the theme is `"auto"`.
 *
 * @param children - React nodes to be rendered inside the provider.
 * @returns The provider's children wrapped in a React fragment.
 */
export function ThemeProvider({ children, themeListener }: ThemeProviderProps) {
  const { theme, setTheme, setIsDark } = useTheme();
  // We can get listener from props OR context
  const { themeListener: contextListener } = useAdapters();
  const listener = themeListener || contextListener;

  useEffect(() => {
    // Load saved theme preference from localStorage (default to 'auto')
    const savedTheme = localStorage.getItem("theme") as Theme | null;
    const initialTheme = savedTheme && ["auto", "light", "dark"].includes(savedTheme)
      ? savedTheme
      : "auto";

    setTheme(initialTheme);
  }, [setTheme]);

  useEffect(() => {
    const applyTheme = () => {
      let shouldBeDark = false;

      if (theme === "dark") {
        shouldBeDark = true;
      } else if (theme === "light") {
        shouldBeDark = false;
      } else if (theme === "auto") {
        // Detect system preference
        shouldBeDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        console.log("[ThemeProvider] System prefers dark mode:", shouldBeDark);
      }

      console.log("[ThemeProvider] Applying theme:", theme, "shouldBeDark:", shouldBeDark);

      // Apply dark class to HTML element
      if (shouldBeDark) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }

      // Update state
      setIsDark(shouldBeDark);

      // Persist theme preference
      localStorage.setItem("theme", theme);
    };

    applyTheme();

    // Listen for system theme changes when in auto mode
    if (theme === "auto") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const handleChange = () => {
        console.log("[ThemeProvider] System theme changed");
        applyTheme();
      };

      // Modern browsers
      mediaQuery.addEventListener("change", handleChange);

      // Listen for platform-specific theme changes (e.g. Tauri, Web)
      // This is optional - if no listener is provided, we just rely on media query
      let unlistenPlatform: (() => void) | undefined;
      
      if (listener) {
        try {
          unlistenPlatform = listener.listen((newTheme) => {
            console.log('[ThemeProvider] Platform theme changed:', newTheme);
            // We don't directly set theme here because we are in 'auto' mode
            // But the platform might be telling us the system preference changed
            applyTheme();
          });
        } catch (error) {
          console.error('[ThemeProvider] Failed to register platform theme listener', error);
        }
      }

      return () => {
        mediaQuery.removeEventListener("change", handleChange);
        if (unlistenPlatform) {
          unlistenPlatform();
        }
      };
    }
  }, [theme, setIsDark, listener]);

  return <>{children}</>;
}