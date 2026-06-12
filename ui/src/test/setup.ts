import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { createRequire } from "module";

const require = createRequire(import.meta.url);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

(
  globalThis as unknown as { jest: typeof vi & { requireActual: unknown } }
).jest = {
  ...vi,
  requireActual: require,
};
