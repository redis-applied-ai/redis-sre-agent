import React from "react";
import { cn } from "../../utils/cn";

export interface NavigationItem {
  label: string;
  href?: string;
  onClick?: () => void;
  isActive?: boolean;
  hidden?: boolean;
}

export interface HeaderProps {
  logo?: React.ReactNode;
  navigationItems?: NavigationItem[];
  rightContent?: React.ReactNode;
  userEmail?: string;
  className?: string;
  variant?: "default" | "compact";
}

export const Header: React.FC<HeaderProps> = ({
  logo,
  navigationItems = [],
  rightContent,
  userEmail,
  className,
  variant = "default",
}) => {
  const paddingClass =
    variant === "compact" ? "px-4 py-2" : "px-4 py-3 sm:px-6 lg:px-8";

  return (
    <header
      className={cn(
        "border-redis-dusk-08 bg-redis-midnight border-b shadow-none",
        className,
      )}
    >
      <div className={cn("flex items-center justify-between", paddingClass)}>
        <div className="flex items-center gap-4 sm:gap-6">
          {logo && (
            <div className="focus:ring-redis-dusk-08 flex-shrink-0 rounded transition hover:opacity-80 focus:outline-none focus:ring-2">
              {logo}
            </div>
          )}

          {navigationItems.length > 0 && (
            <nav className="flex items-center gap-2 sm:gap-4">
              {navigationItems.map((item, index) => {
                if (item.hidden) return null;

                const baseClasses = "text-redis-sm transition-colors";
                const stateClasses = item.isActive
                  ? "text-redis-dusk-01 font-semibold"
                  : "text-redis-dusk-04 font-normal hover:text-redis-dusk-01";

                const content = (
                  <span className={cn(baseClasses, stateClasses)}>
                    {item.label}
                  </span>
                );

                if (item.href) {
                  return (
                    <a key={index} href={item.href} className="block">
                      {content}
                    </a>
                  );
                }

                if (item.onClick) {
                  return (
                    <button
                      key={index}
                      onClick={item.onClick}
                      className="block"
                    >
                      {content}
                    </button>
                  );
                }

                return <span key={index}>{content}</span>;
              })}
            </nav>
          )}
        </div>

        <div className="flex items-center gap-2 sm:gap-4">
          {userEmail && (
            <span className="text-redis-dusk-04 hidden max-w-[150px] truncate text-redis-xs font-normal sm:block md:max-w-none">
              {userEmail}
            </span>
          )}
          {rightContent}
        </div>
      </div>
    </header>
  );
};
