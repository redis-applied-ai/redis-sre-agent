import React from "react";
import { cn } from "../../utils/cn";

export interface ErrorMessageProps {
  message: string;
  title?: string;
  className?: string;
  variant?: "default" | "compact";
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({
  message,
  title,
  className,
  variant = "default",
}) => {
  if (variant === "compact") {
    return (
      <div className={cn("text-redis-xs text-redis-red", className)}>
        {message}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "border-l-4 border-redis-red bg-redis-red/10 p-4 rounded-redis-sm",
        className,
      )}
    >
      <div className="flex">
        <div className="flex-shrink-0">
          <svg
            className="h-5 w-5 text-redis-red"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
        </div>
        <div className="ml-3">
          {title && (
            <h3 className="text-redis-sm font-medium text-redis-red">
              {title}
            </h3>
          )}
          <p className={cn("text-redis-sm text-redis-red/90", title && "mt-1")}>
            {message}
          </p>
        </div>
      </div>
    </div>
  );
};
