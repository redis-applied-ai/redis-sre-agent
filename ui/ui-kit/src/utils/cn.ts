/**
 * Simple utility for conditionally joining classNames together.
 * Alternative to clsx/classnames that's lightweight and type-safe.
 */
export function cn(...inputs: (string | undefined | null | boolean)[]): string {
  return inputs
    .filter(
      (input): input is string =>
        typeof input === "string" && input.trim().length > 0,
    )
    .join(" ");
}
