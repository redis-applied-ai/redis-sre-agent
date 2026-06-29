import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ["react", "react-dom"],
    alias: [
      { find: "@", replacement: resolve(__dirname, "src") },
      { find: "@radar/ui-kit", replacement: resolve(__dirname, "ui-kit/src") },
      {
        find: "@radar/ui-kit/styles",
        replacement: resolve(__dirname, "ui-kit/src/styles/index.css"),
      },
      {
        find: /^@testing-library\/react$/,
        replacement: resolve(__dirname, "node_modules/@testing-library/react"),
      },
      { find: /^react$/, replacement: resolve(__dirname, "node_modules/react") },
      {
        find: /^react\/(.+)$/,
        replacement: resolve(__dirname, "node_modules/react/$1"),
      },
      {
        find: /^react-dom$/,
        replacement: resolve(__dirname, "node_modules/react-dom"),
      },
      {
        find: /^react-dom\/(.+)$/,
        replacement: resolve(__dirname, "node_modules/react-dom/$1"),
      },
    ],
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: [
      "src/**/*.{test,spec}.{ts,tsx}",
      "ui-kit/src/**/*.{test,spec}.{ts,tsx}",
    ],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    setupFiles: "./src/test/setup.ts",
  },
});
