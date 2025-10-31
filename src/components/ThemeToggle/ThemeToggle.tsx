import React from "react";
import { useThemeContext } from "../ThemeProvider/ThemeProvider";
import { Button } from "../Button/Button";

export interface ThemeToggleProps {
  className?: string;
  showLabels?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({
  className,
  showLabels = false,
}) => {
  const { theme, setTheme, resolvedTheme } = useThemeContext();

  const getNextTheme = (currentTheme: string) => {
    switch (currentTheme) {
      case "light":
        return "dark";
      case "dark":
        return "system";
      case "system":
        return "light";
      default:
        return "system";
    }
  };

  const getThemeIcon = () => {
    if (theme === "system") {
      return "🖥️";
    }
    return resolvedTheme === "dark" ? "🌙" : "☀️";
  };

  const getThemeLabel = () => {
    if (theme === "system") {
      return `System (${resolvedTheme})`;
    }
    return theme === "dark" ? "Dark" : "Light";
  };

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => setTheme(getNextTheme(theme))}
      className={className}
      aria-label={`Switch to ${getNextTheme(theme)} theme`}
      title={`Current theme: ${getThemeLabel()}`}
    >
      <span className="mr-2">{getThemeIcon()}</span>
      {showLabels && <span>{theme}</span>}
    </Button>
  );
};
