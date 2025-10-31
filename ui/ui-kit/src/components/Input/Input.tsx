import React from "react";
import { cn } from "../../utils/cn";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, helperText, id, ...props }, ref) => {
    const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`;

    return (
      <div className="form-field w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-redis-sm font-medium text-redis-dusk-01 mb-2"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "redis-input-base w-full",
            error && "border-redis-red focus:ring-redis-red",
            className,
          )}
          {...props}
        />
        {error && (
          <p className="error-text text-redis-xs text-redis-red">{error}</p>
        )}
        {helperText && !error && (
          <p className="helper-text text-redis-xs text-redis-dusk-04">
            {helperText}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = "Input";
