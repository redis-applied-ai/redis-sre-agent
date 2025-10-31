import React, { createContext, useContext } from "react";
import { useTheme, type UseThemeReturn } from "../../hooks/useTheme";

const ThemeContext = createContext<UseThemeReturn | undefined>(undefined);

export interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: "light" | "dark" | "system";
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({
  children,
  defaultTheme = "system",
}) => {
  const themeValue = useTheme();

  // Set default theme if none is stored
  React.useEffect(() => {
    if (
      typeof window !== "undefined" &&
      !localStorage.getItem("redis-ui-theme")
    ) {
      themeValue.setTheme(defaultTheme);
    }
  }, [defaultTheme, themeValue]);

  return (
    <ThemeContext.Provider value={themeValue}>
      <div className="redis-ui-base min-h-screen transition-colors duration-200">
        {children}
      </div>
    </ThemeContext.Provider>
  );
};

export const useThemeContext = (): UseThemeReturn => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useThemeContext must be used within a ThemeProvider");
  }
  return context;
};
