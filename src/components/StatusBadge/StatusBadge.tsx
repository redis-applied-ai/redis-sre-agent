import React from "react";
import { cn } from "../../utils/cn";

export type StatusVariant =
  | "success"
  | "warning"
  | "error"
  | "info"
  | "neutral";

export interface StatusBadgeProps {
  children: React.ReactNode;
  variant?: StatusVariant;
  className?: string;
}

const variantStyles: Record<StatusVariant, string> = {
  success: "text-redis-green-600 bg-redis-green-50 border-redis-green-200",
  warning: "text-redis-yellow-600 bg-redis-yellow-50 border-redis-yellow-200",
  error: "text-redis-red-600 bg-redis-red-50 border-redis-red-200",
  info: "text-redis-blue-600 bg-redis-blue-50 border-redis-blue-200",
  neutral: "text-redis-dusk-04 bg-redis-dusk-07 border-redis-dusk-06",
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  children,
  variant = "neutral",
  className,
}) => {
  return (
    <span
      className={cn(
        "px-2 py-1 rounded-redis-xs text-redis-xs font-medium border",
        variantStyles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
};
