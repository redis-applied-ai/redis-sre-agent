import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { AnalyzerClient } from "./analyzer-client";
import { loadConfig } from "./config";
import { registerNavigationTools } from "./navigation-tools";
import { registerPackageDetailTools } from "./package-detail-tools";
import { AnalyzerApi } from "./types";

export function createServerInfo() {
  return {
    name: "re-analyzer-mcp",
    version: "0.1.0",
  };
}

export function createMcpServer({ analyzerApi }: { analyzerApi: AnalyzerApi }) {
  const server = new McpServer(createServerInfo());
  registerNavigationTools(server, analyzerApi);
  registerPackageDetailTools(server, analyzerApi);
  return server;
}

export async function runStdioServer() {
  const server = createMcpServer({
    analyzerApi: new AnalyzerClient(loadConfig()),
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);

  return server;
}
