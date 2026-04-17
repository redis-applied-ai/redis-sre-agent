import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { createMcpServer, createServerInfo } from "../../src/server";
import { AnalyzerApi } from "../../src/types";

describe("server", () => {
  it("returns the MCP server identity metadata", () => {
    expect(createServerInfo()).toEqual({
      name: "re-analyzer-mcp",
      version: "0.1.0",
    });
  });

  it("registers navigation tools with the MCP server", async () => {
    const api: jest.Mocked<AnalyzerApi> = {
      getApi: jest.fn().mockResolvedValue({ id: "pkg-latest" }),
      getPrivate: jest.fn(),
      postApi: jest.fn(),
    };

    const server = createMcpServer({ analyzerApi: api });
    const client = new Client({ name: "test-client", version: "0.1.0" });
    const [clientTransport, serverTransport] =
      InMemoryTransport.createLinkedPair();

    await server.connect(serverTransport);
    await client.connect(clientTransport);

    const tools = await client.listTools();
    expect(tools.tools.map((tool) => tool.name)).toEqual(
      expect.arrayContaining([
        "analyzer_export_package_json",
        "analyzer_get_account",
        "analyzer_get_cluster",
        "analyzer_get_database_commands",
        "analyzer_get_database_slowlog",
        "analyzer_get_package_alerts",
        "analyzer_get_package_by_hash",
        "analyzer_get_package",
        "analyzer_resolve_package",
        "analyzer_get_cluster_packages",
        "analyzer_get_package_databases",
        "analyzer_get_package_events",
        "analyzer_get_package_health_checks",
        "analyzer_get_package_messages",
        "analyzer_get_latest_cluster_package",
        "analyzer_get_package_nodes",
        "analyzer_get_package_overview",
        "analyzer_get_package_time_series",
        "analyzer_get_package_topology",
        "analyzer_list_accounts",
        "analyzer_list_clusters",
        "analyzer_list_packages",
        "analyzer_search_accounts",
      ]),
    );

    const result = await client.callTool({
      name: "analyzer_get_latest_cluster_package",
      arguments: {
        account_id: "123",
        cluster_name: "cluster-a",
      },
    });

    expect(api.getApi).toHaveBeenCalledWith(
      "/api/clusters/123/cluster-a/packages/latest",
    );
    expect(result.structuredContent).toEqual({
      item: { id: "pkg-latest" },
    });

    await client.close();
    await server.close();
  });
});
