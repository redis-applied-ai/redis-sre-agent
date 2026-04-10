import { createPackageDetailToolHandlers } from "../../src/package-detail-tools";
import { AnalyzerApi } from "../../src/types";

describe("createPackageDetailToolHandlers", () => {
  function createApi(): jest.Mocked<AnalyzerApi> {
    return {
      getApi: jest.fn(),
      getPrivate: jest.fn(),
      postApi: jest.fn(),
    };
  }

  it("retrieves package alerts with default sources and MCP-side truncation", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { id: "alert-1", status: "active" },
      { id: "alert-2", status: "active" },
    ]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_package_alerts({
      package_id: "pkg-1",
      limit: 1,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/data/pkg-1/alerts", {
      sources: ["cluster", "node", "bdb", "BDB"],
      status: "active",
    });
    expect(result.structuredContent).toEqual({
      count: 2,
      items: [{ id: "alert-1", status: "active" }],
      truncated: true,
    });
  });

  it("filters OK health checks by default and returns status counts", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { id: "hc-1", status: "OK" },
      { id: "hc-2", status: "WARNING" },
      { id: "hc-3", status: "CRITICAL" },
    ]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_package_health_checks({
      package_id: "pkg-1",
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/health-check/pkg-1/results");
    expect(result.structuredContent).toEqual({
      count: 2,
      counts_by_status: {
        CRITICAL: 1,
        OK: 1,
        WARNING: 1,
      },
      items: [
        { id: "hc-2", status: "WARNING" },
        { id: "hc-3", status: "CRITICAL" },
      ],
      truncated: false,
    });
  });

  it("discovers event sources when needed and posts the event search", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue(["cluster", "node"]);
    api.postApi.mockResolvedValue([{ id: "event-1" }]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_package_events({
      package_id: "pkg-1",
      severity: [40, 50],
      since_date: "2024-03-01T00:00:00.000Z",
      limit: 50,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/data/pkg-1/events/list");
    expect(api.postApi).toHaveBeenCalledWith("/api/data/pkg-1/events/search", {
      limit: 50,
      severity: [40, 50],
      sinceDate: "2024-03-01T00:00:00.000Z",
      sources: ["cluster", "node"],
    });
    expect(result.structuredContent).toEqual({
      count: 1,
      items: [{ id: "event-1" }],
      source_list: ["cluster", "node"],
    });
  });

  it("filters database results and only includes requested sections", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      {
        id: 1,
        name: "db-1",
        status: "active",
        type: "redis",
        port: 12000,
        shards: [{ id: "redis-1" }],
        endpoints: [{ id: "1:1" }],
        commands: ["get"],
        modules: [{ name: "search" }],
        replicas: [{ id: "replica-1" }],
        memory_size: 1024,
      },
      {
        id: 2,
        name: "db-2",
        status: "active",
        type: "redis",
        port: 12001,
        shards: [{ id: "redis-2" }],
        endpoints: [{ id: "2:1" }],
        commands: ["set"],
        modules: [{ name: "json" }],
        replicas: [{ id: "replica-2" }],
        memory_size: 2048,
      },
    ]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_package_databases({
      package_id: "pkg-1",
      database_ids: [2],
      include_modules: false,
      include_replicas: true,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/data/pkg-1/bdbs");
    expect(result.structuredContent).toEqual({
      count: 1,
      items: [
        {
          command_names: ["set"],
          endpoint_ids: ["2:1"],
          id: 2,
          name: "db-2",
          port: 12001,
          replicas: [{ id: "replica-2" }],
          shards_count: 1,
          status: "active",
          type: "redis",
        },
      ],
      truncated: false,
    });
  });

  it("sorts slowlog entries newest first and truncates them", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { timestamp: 1, entry: "old" },
      { timestamp: 3, entry: "new" },
    ]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_database_slowlog({
      package_id: "pkg-1",
      database_id: 7,
      limit: 1,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/data/pkg-1/bdbs/7/slowlog");
    expect(result.structuredContent).toEqual({
      count: 1,
      items: [{ entry: "new", timestamp: 3 }],
      truncated: true,
    });
  });

  it("sorts commands by activity and truncates them", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { name: "set", calls: 20, usec: 30 },
      { name: "get", calls: 50, usec: 10 },
    ]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_database_commands({
      package_id: "pkg-1",
      database_id: 7,
      limit: 1,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/data/pkg-1/bdbs/7/commands");
    expect(result.structuredContent).toEqual({
      count: 1,
      items: [{ calls: 50, name: "get", usec: 10 }],
      truncated: true,
    });
  });

  it("filters package nodes and strips shard lists when requested", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { id: 1, shortHostname: "node-1", shards: [{ id: "redis-1" }] },
      { id: 2, shortHostname: "node-2", shards: [{ id: "redis-2" }] },
    ]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_package_nodes({
      package_id: "pkg-1",
      node_ids: [2],
      include_shards: false,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/data/pkg-1/nodes");
    expect(result.structuredContent).toEqual({
      count: 1,
      items: [{ id: 2, shortHostname: "node-2" }],
      truncated: false,
    });
  });

  it("builds a topology view with placement summaries", async () => {
    const api = createApi();
    api.getApi.mockImplementation(async (path: string) => {
      switch (path) {
        case "/api/data/pkg-1/cluster":
          return { name: "cluster-a" };
        case "/api/data/pkg-1/bdbs":
          return [
            {
              id: 1,
              name: "db-1",
              endpoints: [{ id: "1:1", proxy: [1, 2] }],
              shards: [
                { id: "redis-1", nodeUid: 1, role: "master" },
                { id: "redis-2", nodeUid: 2, role: "slave" },
              ],
            },
          ];
        case "/api/data/pkg-1/nodes":
          return [
            { id: 1, shortHostname: "node-1" },
            { id: 2, shortHostname: "node-2" },
          ];
        case "/api/data/pkg-1/endpoints":
          return [{ id: "1:1", proxy: [1, 2] }];
        default:
          throw new Error(`Unexpected path: ${path}`);
      }
    });

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_package_topology({
      package_id: "pkg-1",
    });

    expect(result.structuredContent).toEqual({
      details: {
        cluster: { name: "cluster-a" },
        databases: [
          {
            endpoints: [{ id: "1:1", proxy: [1, 2] }],
            id: 1,
            name: "db-1",
            shards: [
              { id: "redis-1", nodeUid: 1, role: "master" },
              { id: "redis-2", nodeUid: 2, role: "slave" },
            ],
          },
        ],
        endpoints: [{ id: "1:1", proxy: [1, 2] }],
        nodes: [
          { id: 1, shortHostname: "node-1" },
          { id: 2, shortHostname: "node-2" },
        ],
      },
      placement_summary: [
        {
          database_id: 1,
          database_name: "db-1",
          endpoint_ids: ["1:1"],
          endpoint_node_ids: [1, 2],
          shard_placements: [
            { node_id: 1, role: "master", shard_id: "redis-1" },
            { node_id: 2, role: "slave", shard_id: "redis-2" },
          ],
        },
      ],
      summary: {
        database_count: 1,
        endpoint_count: 1,
        node_count: 2,
      },
    });
  });

  it("retrieves package time series for a requested scope", async () => {
    const api = createApi();
    api.getApi
      .mockResolvedValueOnce({ from: 1, to: 2 })
      .mockResolvedValueOnce([{ stime: 1, etime: 2, used_memory: 100 }]);

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_get_package_time_series({
      package_id: "pkg-1",
      scope: "node",
      scope_id: "2",
      interval: "last hour",
    });

    expect(api.getApi).toHaveBeenNthCalledWith(
      1,
      "/api/time-series/pkg-1/interval",
    );
    expect(api.getApi).toHaveBeenNthCalledWith(
      2,
      "/api/time-series/pkg-1/nodes/2/stats/last%20hour",
    );
    expect(result.structuredContent).toEqual({
      interval: { from: 1, to: 2 },
      items: [{ etime: 2, stime: 1, used_memory: 100 }],
      scope: "node",
      scope_id: "2",
    });
  });

  it("exports the normalized package JSON", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue({
      id: "pkg-1",
      cluster: { name: "cluster-a" },
    });

    const handlers = createPackageDetailToolHandlers(api);
    const result = await handlers.analyzer_export_package_json({
      package_id: "pkg-1",
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/export/package/pkg-1");
    expect(result.structuredContent).toEqual({
      item: {
        cluster: { name: "cluster-a" },
        id: "pkg-1",
      },
    });
  });
});
