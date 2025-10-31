import React, { useState, useCallback } from "react";
import { Button } from "../Button/Button";
import { ErrorMessage } from "../ErrorMessage/ErrorMessage";
import { FormField, type Option } from "./FormField";
import { cn } from "../../utils/cn";

export interface FormFieldConfig {
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
  placeholder?: string;
  options?: Option[];
  required?: boolean;
  disabled?: boolean;
  helperText?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  validation?: (value: any) => string | undefined;
}

export interface FormProps {
  fields: FormFieldConfig[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  initialData?: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onSubmit: (data: Record<string, any>) => Promise<void> | void;
  onCancel?: () => void;
  submitLabel?: string;
  cancelLabel?: string;
  isLoading?: boolean;
  className?: string;
  title?: string;
  description?: string;
  layout?: "vertical" | "horizontal";
}

export const Form: React.FC<FormProps> = ({
  fields,
  initialData = {},
  onSubmit,
  onCancel,
  submitLabel = "Submit",
  cancelLabel = "Cancel",
  isLoading = false,
  className,
  title,
  description,
  layout = "vertical",
}) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [formData, setFormData] = useState<Record<string, any>>(initialData);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string>("");

  const handleFieldChange = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (fieldName: string, value: any) => {
      setFormData((prev) => ({
        ...prev,
        [fieldName]: value,
      }));

      // Clear field error when user starts typing
      if (errors[fieldName]) {
        setErrors((prev) => {
          const newErrors = { ...prev };
          delete newErrors[fieldName];
          return newErrors;
        });
      }
    },
    [errors],
  );

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    fields.forEach((field) => {
      const value = formData[field.name];

      // Required validation
      if (field.required) {
        if (
          value === undefined ||
          value === null ||
          value === "" ||
          (Array.isArray(value) && value.length === 0)
        ) {
          newErrors[field.name] = `${field.label || field.name} is required`;
          return;
        }
      }

      // Custom validation
      if (
        field.validation &&
        value !== undefined &&
        value !== null &&
        value !== ""
      ) {
        const validationError = field.validation(value);
        if (validationError) {
          newErrors[field.name] = validationError;
        }
      }
    });

    return newErrors;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError("");

    const validationErrors = validateForm();
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setErrors({});

    try {
      await onSubmit(formData);
    } catch (error) {
      console.error("Form submission error:", error);
      setSubmitError(
        error instanceof Error ? error.message : "An error occurred",
      );
    }
  };

  const layoutClasses =
    layout === "horizontal"
      ? "grid grid-cols-1 md:grid-cols-2 gap-3"
      : "space-y-3";

  return (
    <div className={cn("w-full", className)}>
      {(title || description) && (
        <div className="mb-6">
          {title && (
            <h2 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
              {title}
            </h2>
          )}
          {description && (
            <p className="text-redis-sm text-redis-dusk-04">{description}</p>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="w-full">
        {submitError && (
          <div className="mb-4">
            <ErrorMessage message={submitError} />
          </div>
        )}

        <div className={layoutClasses}>
          {fields.map((field) => (
            <FormField
              key={field.name}
              {...field}
              value={formData[field.name]}
              error={errors[field.name]}
              onChange={(value) => handleFieldChange(field.name, value)}
            />
          ))}
        </div>

        <div className="flex justify-end space-x-3 mt-6">
          {onCancel && (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isLoading}
            >
              {cancelLabel}
            </Button>
          )}
          <Button
            type="submit"
            variant="primary"
            isLoading={isLoading}
            disabled={isLoading}
          >
            {isLoading ? "Saving..." : submitLabel}
          </Button>
        </div>
      </form>
    </div>
  );
};
