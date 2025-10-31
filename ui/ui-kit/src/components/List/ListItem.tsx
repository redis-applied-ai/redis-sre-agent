import React from "react";
import { cn } from "../../utils/cn";

export interface ListItemProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  selected?: boolean;
  className?: string;
  variant?: "default" | "compact";
}

export const ListItem = React.forwardRef<HTMLButtonElement, ListItemProps>(
  (
    { children, selected = false, className, variant = "default", ...props },
    ref,
  ) => {
    const baseClasses = `
      w-full text-left rounded-redis-sm hover:bg-redis-dusk-09
      transition-colors focus:outline-none focus:ring-2
      focus:ring-redis-blue-03/50 focus:ring-offset-2
      focus:ring-offset-redis-dusk-10
    `;

    const variantClasses = {
      default: "p-3 m-2",
      compact: "p-2 mx-2 my-1",
    };

    const selectedClasses = selected ? "bg-redis-dusk-09" : "";

    return (
      <button
        ref={ref}
        className={cn(
          baseClasses,
          variantClasses[variant],
          selectedClasses,
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);

ListItem.displayName = "ListItem";
