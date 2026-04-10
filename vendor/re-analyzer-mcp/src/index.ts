#!/usr/bin/env node

export * from "./analyzer-client";
export * from "./config";
export * from "./navigation-tools";
export * from "./package-detail-tools";
export * from "./server";
export * from "./tool-utils";
export * from "./types";

if (require.main === module) {
  runMain().catch((error: unknown) => {
    const message =
      error instanceof Error ? (error.stack ?? error.message) : String(error);
    process.stderr.write(`${message}\n`);
    process.exit(1);
  });
}

async function runMain() {
  const { runStdioServer } = await import("./server");
  await runStdioServer();
}
