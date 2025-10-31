import { useEffect, useState } from "react";

export type Theme = "light" | "dark" | "system";

export interface UseThemeReturn {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
}

export function useTheme(): UseThemeReturn {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("redis-ui-theme") as Theme) || "system";
    }
    return "system";
  });

  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() => {
    if (typeof window !== "undefined") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      return mediaQuery.matches ? "dark" : "light";
    }
    return "light";
  });

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    if (typeof window !== "undefined") {
      localStorage.setItem("redis-ui-theme", newTheme);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return;

    const updateResolvedTheme = () => {
      if (theme === "system") {
        const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
        setResolvedTheme(mediaQuery.matches ? "dark" : "light");
      } else {
        setResolvedTheme(theme as "light" | "dark");
      }
    };

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => {
      if (theme === "system") {
        setResolvedTheme(mediaQuery.matches ? "dark" : "light");
      }
    };

    // Set initial resolved theme
    updateResolvedTheme();

    // Listen for system theme changes
    mediaQuery.addEventListener("change", handleChange);

    return () => {
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, [theme]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const root = document.documentElement;

    // Remove existing theme classes
    root.classList.remove("theme-light", "theme-dark");

    // Add appropriate theme class
    if (theme !== "system") {
      root.classList.add(`theme-${theme}`);
    }
    // If theme is 'system', let CSS media query handle it naturally
  }, [theme, resolvedTheme]);

  return { theme, resolvedTheme, setTheme };
}
