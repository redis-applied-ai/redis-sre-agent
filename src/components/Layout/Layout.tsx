import React from "react";
import { cn } from "../../utils/cn";

export interface LayoutProps {
  children: React.ReactNode;
  header?: React.ReactNode;
  sidebar?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  contentClassName?: string;
  variant?: "default" | "centered" | "full-width";
  backgroundColor?: string;
}

export const Layout: React.FC<LayoutProps> = ({
  children,
  header,
  sidebar,
  footer,
  className,
  contentClassName,
  variant = "default",
  backgroundColor,
}) => {
  const getContentClasses = () => {
    const base = "flex flex-1";

    switch (variant) {
      case "centered":
        return cn(base, "items-center justify-center");
      case "full-width":
        return cn(base, "w-full");
      default:
        return cn(base, "items-center justify-center");
    }
  };

  const getInnerContentClasses = () => {
    const base = "font-geist w-full px-4 pb-10 pt-6 lg:px-10";

    switch (variant) {
      case "full-width":
        return base;
      case "centered":
        return cn(base, "min-h-[70vh] max-w-6xl");
      default:
        return cn(base, "min-h-[70vh] max-w-6xl");
    }
  };

  return (
    <div
      className={cn("flex min-h-screen flex-col", className)}
      style={backgroundColor ? { backgroundColor } : undefined}
      data-testid="layout-container"
    >
      {header}

      <div className="flex flex-1">
        {sidebar && <aside className="w-64 flex-shrink-0">{sidebar}</aside>}

        <main className={cn(getContentClasses(), "bg-inherit")}>
          <div className={cn(getInnerContentClasses(), contentClassName)}>
            {children}
          </div>
        </main>
      </div>

      {footer}
    </div>
  );
};
