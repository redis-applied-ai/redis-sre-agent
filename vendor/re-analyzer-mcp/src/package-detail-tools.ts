import * as z from "zod/v4";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { AnalyzerApi } from "./types";
import { getEntityId, toToolResponse, truncateItems } from "./tool-utils";

const alertSourceSchema = z.enum(["cluster", "node", "bdb", "BDB"]);
const timeSeriesScopeSchema = z.enum(["cluster", "node", "endpoint", "shard"]);
const timeSeriesIntervalSchema = z.enum([
  "all",
  "last 30 days",
  "last 7 days",
  "last 24 hours",
  "last hour",
  "last 5 minutes",
]);

const DEFAULT_ALERT_SOURCES = ["cluster", "node", "bdb", "BDB"] as const;

function countByStatus(items: Array<Record<string, unknown>>) {
  return items.reduce<Record<string, number>>((counts, item) => {
    const status = typeof item.status === "string" ? item.status : "UNKNOWN";
    counts[status] = (counts[status] ?? 0) + 1;
    return counts;
  }, {});
}

function summarizeDatabase(
  database: Record<string, unknown>,
  options: {
    includeConfig: boolean;
    includeModules: boolean;
    includeReplicas: boolean;
  },
) {
  const summary: Record<string, unknown> = {
    id: database.id,
    name: database.name,
    status: database.status,
    type: database.type,
    port: database.port,
    shards_count: Array.isArray(database.shards)
      ? database.shards.length
      : database.shardsCount,
    endpoint_ids: Array.isArray(database.endpoints)
      ? database.endpoints
          .map((endpoint) =>
            typeof endpoint === "object" && endpoint !== null
              ? getEntityId(endpoint as Record<string, unknown>)
              : undefined,
          )
          .filter(
            (endpointId): endpointId is number | string =>
              endpointId !== undefined,
          )
      : [],
    command_names: Array.isArray(database.commands) ? database.commands : [],
  };

  if (options.includeModules && Array.isArray(database.modules)) {
    summary.modules = database.modules;
  }

  if (options.includeReplicas && Array.isArray(database.replicas)) {
    summary.replicas = database.replicas;
  }

  if (options.includeConfig) {
    summary.config = database;
  }

  return summary;
}

function buildTopologyPlacementSummary(
  databases: Array<Record<string, unknown>>,
) {
  return databases.map((database) => {
    const endpoints = Array.isArray(database.endpoints)
      ? database.endpoints.filter(
          (endpoint): endpoint is Record<string, unknown> =>
            typeof endpoint === "object" && endpoint !== null,
        )
      : [];
    const shards = Array.isArray(database.shards)
      ? database.shards.filter(
          (shard): shard is Record<string, unknown> =>
            typeof shard === "object" && shard !== null,
        )
      : [];

    const endpointNodeIds = Array.from(
      new Set(
        endpoints.flatMap((endpoint) =>
          Array.isArray(endpoint.proxy)
            ? endpoint.proxy.filter(
                (nodeId): nodeId is number => typeof nodeId === "number",
              )
            : [],
        ),
      ),
    );

    return {
      database_id: database.id,
      database_name: database.name,
      endpoint_ids: endpoints
        .map((endpoint) => getEntityId(endpoint))
        .filter(
          (endpointId): endpointId is number | string =>
            endpointId !== undefined,
        ),
      endpoint_node_ids: endpointNodeIds,
      shard_placements: shards.map((shard) => ({
        shard_id: shard.id,
        node_id: shard.nodeUid ?? shard.node_id,
        role: shard.role,
      })),
    };
  });
}

function getTimeSeriesPath(args: {
  package_id: string;
  scope: z.infer<typeof timeSeriesScopeSchema>;
  scope_id?: string;
  interval: z.infer<typeof timeSeriesIntervalSchema>;
}) {
  const packageId = encodeURIComponent(args.package_id);
  const interval = encodeURIComponent(args.interval);

  switch (args.scope) {
    case "cluster":
      return `/api/time-series/${packageId}/cluster/stats/${interval}`;
    case "node":
      if (!args.scope_id) {
        throw new Error("scope_id is required for node time series");
      }
      return `/api/time-series/${packageId}/nodes/${encodeURIComponent(args.scope_id)}/stats/${interval}`;
    case "endpoint":
      if (!args.scope_id) {
        throw new Error("scope_id is required for endpoint time series");
      }
      return `/api/time-series/${packageId}/endpoints/${encodeURIComponent(args.scope_id)}/stats/${interval}`;
    case "shard":
      if (!args.scope_id) {
        throw new Error("scope_id is required for shard time series");
      }
      return `/api/time-series/${packageId}/redis/${encodeURIComponent(args.scope_id)}/stats/${interval}`;
  }
}

export function createPackageDetailToolHandlers(analyzerApi: AnalyzerApi) {
  return {
    analyzer_get_package_alerts: async (args: {
      package_id: string;
      sources?: Array<z.infer<typeof alertSourceSchema>>;
      status?: "active" | "inactive" | "all";
      enabled?: string;
      state?: "on" | "off" | "all";
      node_id?: number;
      database_id?: number;
      limit?: number;
    }) => {
      const alerts = await analyzerApi.getApi<Array<Record<string, unknown>>>(
        `/api/data/${encodeURIComponent(args.package_id)}/alerts`,
        {
          ...(args.sources
            ? { sources: args.sources }
            : { sources: [...DEFAULT_ALERT_SOURCES] }),
          status: args.status ?? "active",
          ...(args.enabled ? { enabled: args.enabled } : {}),
          ...(args.state ? { state: args.state } : {}),
          ...(args.node_id !== undefined
            ? { nodeId: String(args.node_id) }
            : {}),
          ...(args.database_id !== undefined
            ? { databaseId: String(args.database_id) }
            : {}),
        },
      );

      return toToolResponse(truncateItems(alerts, args.limit ?? 100));
    },

    analyzer_get_package_health_checks: async (args: {
      package_id: string;
      include_ok?: boolean;
      limit?: number;
    }) => {
      const healthChecks = await analyzerApi.getApi<
        Array<Record<string, unknown>>
      >(`/api/health-check/${encodeURIComponent(args.package_id)}/results`);
      const items = args.include_ok
        ? healthChecks
        : healthChecks.filter((item) => item.status !== "OK");

      return toToolResponse({
        ...truncateItems(items, args.limit ?? 100),
        counts_by_status: countByStatus(healthChecks),
      });
    },

    analyzer_get_package_events: async (args: {
      package_id: string;
      sources?: string[];
      severity?: number[];
      since_date?: string;
      limit?: number;
    }) => {
      const sources =
        args.sources ??
        (await analyzerApi.getApi<string[]>(
          `/api/data/${encodeURIComponent(args.package_id)}/events/list`,
        ));

      const items = await analyzerApi.postApi<Array<Record<string, unknown>>>(
        `/api/data/${encodeURIComponent(args.package_id)}/events/search`,
        {
          sources,
          ...(args.severity ? { severity: args.severity } : {}),
          ...(args.since_date ? { sinceDate: args.since_date } : {}),
          ...(args.limit ? { limit: args.limit } : {}),
        },
      );

      return toToolResponse({
        items,
        count: items.length,
        source_list: sources,
      });
    },

    analyzer_get_package_databases: async (args: {
      package_id: string;
      database_ids?: number[];
      include_config?: boolean;
      include_modules?: boolean;
      include_replicas?: boolean;
    }) => {
      const databases = await analyzerApi.getApi<
        Array<Record<string, unknown>>
      >(`/api/data/${encodeURIComponent(args.package_id)}/bdbs`);
      const filtered = args.database_ids?.length
        ? databases.filter((database) =>
            args.database_ids?.includes(Number(database.id ?? database.uid)),
          )
        : databases;
      const items = filtered.map((database) =>
        summarizeDatabase(database, {
          includeConfig: args.include_config ?? false,
          includeModules: args.include_modules ?? true,
          includeReplicas: args.include_replicas ?? true,
        }),
      );

      return toToolResponse(truncateItems(items, items.length || 100));
    },

    analyzer_get_database_slowlog: async (args: {
      package_id: string;
      database_id: number;
      limit?: number;
    }) => {
      const slowlog = await analyzerApi.getApi<Array<Record<string, unknown>>>(
        `/api/data/${encodeURIComponent(args.package_id)}/bdbs/${args.database_id}/slowlog`,
      );
      const items = slowlog.sort(
        (left, right) =>
          Number(right.timestamp ?? 0) - Number(left.timestamp ?? 0),
      );
      const limited = items.slice(0, args.limit ?? 200);

      return toToolResponse({
        items: limited,
        count: limited.length,
        truncated: items.length > limited.length,
      });
    },

    analyzer_get_database_commands: async (args: {
      package_id: string;
      database_id: number;
      limit?: number;
    }) => {
      const commands = await analyzerApi.getApi<Array<Record<string, unknown>>>(
        `/api/data/${encodeURIComponent(args.package_id)}/bdbs/${args.database_id}/commands`,
      );
      const items = commands.sort((left, right) => {
        const callsDiff = Number(right.calls ?? 0) - Number(left.calls ?? 0);
        if (callsDiff !== 0) {
          return callsDiff;
        }

        return Number(right.usec ?? 0) - Number(left.usec ?? 0);
      });
      const limited = items.slice(0, args.limit ?? 50);

      return toToolResponse({
        items: limited,
        count: limited.length,
        truncated: items.length > limited.length,
      });
    },

    analyzer_get_package_nodes: async (args: {
      package_id: string;
      node_ids?: number[];
      include_shards?: boolean;
    }) => {
      const nodes = await analyzerApi.getApi<Array<Record<string, unknown>>>(
        `/api/data/${encodeURIComponent(args.package_id)}/nodes`,
      );
      const filtered = args.node_ids?.length
        ? nodes.filter((node) =>
            args.node_ids?.includes(Number(node.id ?? node.uid)),
          )
        : nodes;
      const items = filtered.map((node) => {
        if (args.include_shards ?? true) {
          return node;
        }

        const { shards: _shards, ...rest } = node;
        return rest;
      });

      return toToolResponse(truncateItems(items, items.length || 100));
    },

    analyzer_get_package_topology: async (args: { package_id: string }) => {
      const [cluster, databases, nodes, endpoints] = await Promise.all([
        analyzerApi.getApi<Record<string, unknown> | null>(
          `/api/data/${encodeURIComponent(args.package_id)}/cluster`,
        ),
        analyzerApi.getApi<Array<Record<string, unknown>>>(
          `/api/data/${encodeURIComponent(args.package_id)}/bdbs`,
        ),
        analyzerApi.getApi<Array<Record<string, unknown>>>(
          `/api/data/${encodeURIComponent(args.package_id)}/nodes`,
        ),
        analyzerApi.getApi<Array<Record<string, unknown>>>(
          `/api/data/${encodeURIComponent(args.package_id)}/endpoints`,
        ),
      ]);

      return toToolResponse({
        summary: {
          database_count: databases.length,
          node_count: nodes.length,
          endpoint_count: endpoints.length,
        },
        details: {
          cluster,
          databases,
          nodes,
          endpoints,
        },
        placement_summary: buildTopologyPlacementSummary(databases),
      });
    },

    analyzer_get_package_time_series: async (args: {
      package_id: string;
      scope: z.infer<typeof timeSeriesScopeSchema>;
      scope_id?: string;
      interval: z.infer<typeof timeSeriesIntervalSchema>;
    }) => {
      const interval = await analyzerApi.getApi<Record<string, unknown>>(
        `/api/time-series/${encodeURIComponent(args.package_id)}/interval`,
      );
      const items = await analyzerApi.getApi<Array<Record<string, unknown>>>(
        getTimeSeriesPath(args),
      );

      return toToolResponse({
        interval,
        items,
        scope: args.scope,
        ...(args.scope_id ? { scope_id: args.scope_id } : {}),
      });
    },

    analyzer_export_package_json: async (args: { package_id: string }) => {
      const item = await analyzerApi.getApi<Record<string, unknown>>(
        `/api/export/package/${encodeURIComponent(args.package_id)}`,
      );

      return toToolResponse({ item });
    },
  };
}

export function registerPackageDetailTools(
  server: McpServer,
  analyzerApi: AnalyzerApi,
) {
  const handlers = createPackageDetailToolHandlers(analyzerApi);

  server.registerTool(
    "analyzer_get_package_alerts",
    {
      description: "Retrieve package alerts with useful MCP-side filtering.",
      inputSchema: {
        package_id: z.string(),
        sources: z.array(alertSourceSchema).optional(),
        status: z.enum(["active", "inactive", "all"]).optional(),
        enabled: z.string().optional(),
        state: z.enum(["on", "off", "all"]).optional(),
        node_id: z.number().int().optional(),
        database_id: z.number().int().optional(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_package_alerts,
  );

  server.registerTool(
    "analyzer_get_package_health_checks",
    {
      description:
        "Retrieve package health-check results in a form suited for triage.",
      inputSchema: {
        package_id: z.string(),
        include_ok: z.boolean().optional(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_package_health_checks,
  );

  server.registerTool(
    "analyzer_get_package_events",
    {
      description:
        "Search structured package events by source, severity, and time window.",
      inputSchema: {
        package_id: z.string(),
        sources: z.array(z.string()).optional(),
        severity: z.array(z.number()).optional(),
        since_date: z.string().optional(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_package_events,
  );

  server.registerTool(
    "analyzer_get_package_databases",
    {
      description: "Retrieve package databases and their key metadata.",
      inputSchema: {
        package_id: z.string(),
        database_ids: z.array(z.number().int()).optional(),
        include_config: z.boolean().optional(),
        include_modules: z.boolean().optional(),
        include_replicas: z.boolean().optional(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_package_databases,
  );

  server.registerTool(
    "analyzer_get_database_slowlog",
    {
      description: "Retrieve slowlog entries for one database in one package.",
      inputSchema: {
        package_id: z.string(),
        database_id: z.number().int(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_database_slowlog,
  );

  server.registerTool(
    "analyzer_get_database_commands",
    {
      description:
        "Retrieve command statistics for one database in one package.",
      inputSchema: {
        package_id: z.string(),
        database_id: z.number().int(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_database_commands,
  );

  server.registerTool(
    "analyzer_get_package_nodes",
    {
      description: "Retrieve nodes and shard placement for one package.",
      inputSchema: {
        package_id: z.string(),
        node_ids: z.array(z.number().int()).optional(),
        include_shards: z.boolean().optional(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_package_nodes,
  );

  server.registerTool(
    "analyzer_get_package_topology",
    {
      description:
        "Return a topology-oriented package view for agent reasoning.",
      inputSchema: {
        package_id: z.string(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_package_topology,
  );

  server.registerTool(
    "analyzer_get_package_time_series",
    {
      description:
        "Retrieve time-series samples for cluster, node, endpoint, or shard scope.",
      inputSchema: {
        package_id: z.string(),
        scope: timeSeriesScopeSchema,
        scope_id: z.string().optional(),
        interval: timeSeriesIntervalSchema,
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_get_package_time_series,
  );

  server.registerTool(
    "analyzer_export_package_json",
    {
      description:
        "Export the normalized package representation as one JSON object.",
      inputSchema: {
        package_id: z.string(),
      },
      annotations: { readOnlyHint: true },
    },
    handlers.analyzer_export_package_json,
  );
}
