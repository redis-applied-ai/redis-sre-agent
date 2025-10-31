import React from "react";
import { Input } from "../Input/Input";
import { cn } from "../../utils/cn";

export interface Option {
  label: string;
  value: string | number;
  disabled?: boolean;
}

export interface FormFieldProps {
  name: string;
  label?: string;
  type?:
    | "text"
    | "email"
    | "password"
    | "number"
    | "tel"
    | "date"
    | "select"
    | "checkbox"
    | "textarea";
  value?: string | number | string[];
  placeholder?: string;
  options?: Option[];
  error?: string;
  helperText?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onChange?: (value: any) => void;
  onBlur?: () => void;
}

export const FormField: React.FC<FormFieldProps> = ({
  name,
  label,
  type = "text",
  value,
  placeholder,
  options = [],
  error,
  helperText,
  required = false,
  disabled = false,
  className,
  onChange,
  onBlur,
}) => {
  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >,
  ) => {
    if (!onChange) return;

    if (type === "checkbox") {
      const target = e.target as HTMLInputElement;
      const currentValues = Array.isArray(value) ? value : [];
      const newValues = target.checked
        ? [...currentValues, target.value]
        : currentValues.filter((v) => v !== target.value);
      onChange(newValues);
    } else {
      onChange(e.target.value);
    }
  };

  const getFieldId = () => `field-${name}`;

  if (type === "select") {
    return (
      <div className={cn("form-field w-full", className)}>
        {label && (
          <label
            htmlFor={getFieldId()}
            className="block text-redis-sm font-medium text-redis-dusk-01 mb-2"
          >
            {label} {required && <span className="text-redis-red">*</span>}
          </label>
        )}
        <select
          id={getFieldId()}
          name={name}
          value={value || ""}
          onChange={handleChange}
          onBlur={onBlur}
          disabled={disabled}
          className={cn(
            "redis-input-base w-full",
            error && "border-redis-red focus:ring-redis-red",
          )}
        >
          <option value="">{placeholder || `Select ${label}`}</option>
          {options.map((option) => (
            <option
              key={option.value}
              value={option.value}
              disabled={option.disabled}
            >
              {option.label}
            </option>
          ))}
        </select>
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
  }

  if (type === "checkbox" && options.length > 0) {
    const checkedValues = Array.isArray(value) ? value : [];

    return (
      <div className={cn("form-field w-full", className)}>
        {label && (
          <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-2">
            {label} {required && <span className="text-redis-red">*</span>}
          </label>
        )}
        <div className="flex flex-col">
          {options.map((option) => (
            <label key={option.value} className="flex items-center gap-3 py-2">
              <input
                type="checkbox"
                name={name}
                value={option.value}
                checked={checkedValues.includes(String(option.value))}
                onChange={handleChange}
                onBlur={onBlur}
                disabled={disabled || option.disabled}
                className="checkbox-base"
              />
              <span className="text-redis-sm text-redis-dusk-01">
                {option.label}
              </span>
            </label>
          ))}
        </div>
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
  }

  if (type === "textarea") {
    return (
      <div className={cn("form-field w-full", className)}>
        {label && (
          <label
            htmlFor={getFieldId()}
            className="block text-redis-sm font-medium text-redis-dusk-01 mb-2"
          >
            {label} {required && <span className="text-redis-red">*</span>}
          </label>
        )}
        <textarea
          id={getFieldId()}
          name={name}
          value={value || ""}
          placeholder={placeholder}
          onChange={handleChange}
          onBlur={onBlur}
          disabled={disabled}
          rows={4}
          className={cn(
            "redis-input-base w-full resize-vertical",
            error && "border-redis-red focus:ring-redis-red",
          )}
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
  }

  return (
    <Input
      id={getFieldId()}
      label={required ? `${label} *` : label}
      type={type}
      value={value as string}
      placeholder={placeholder}
      error={error}
      helperText={helperText}
      disabled={disabled}
      className={className}
      onChange={(e) => onChange?.(e.target.value)}
      onBlur={onBlur}
    />
  );
};
