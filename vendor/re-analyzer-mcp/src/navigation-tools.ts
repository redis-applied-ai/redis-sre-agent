import * as z from "zod/v4";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { AnalyzerApi, McpToolResponse } from "./types";
import {
  ProcessStatusSummary,
  getEntityId,
  summarizeProcessStatus,
  toToolResponse,
  truncateItems,
} from "./tool-utils";

const overviewSectionSchema = z.enum([
  "cluster",
  "databases",
  "nodes",
  "tasks",
  "alerts",
  "health_checks",
]);

type OverviewSection = z.infer<typeof overviewSectionSchema>;

function toSearchableText(value: unknown) {
  return typeof value === "string" ? value.toLowerCase() : "";
}

function matchesSubstring(value: unknown, query?: string) {
  if (!query) {
    return true;
  }

  return toSearchableText(value).includes(query.toLowerCase());
}

function summarizeHealthCheckStatus(statusMaps: Array<Record<string, number>>) {
  const labels = ["data", "timeseries", "log"] as const;
  const byDatabase = labels.reduce<
    Record<(typeof labels)[number], ProcessStatusSummary>
  >(
    (summary, label, index) => {
      summary[label] = summarizeProcessStatus(statusMaps[index] ?? {});
      return summary;
    },
    {} as Record<(typeof labels)[number], ProcessStatusSummary>,
  );

  return {
    by_database: byDatabase,
    total: Object.values(byDatabase).reduce<ProcessStatusSummary>(
      (summary, databaseSummary) => ({
        scheduled: summary.scheduled + databaseSummary.scheduled,
        in_progress: summary.in_progress + databaseSummary.in_progress,
        parsed: summary.parsed + databaseSummary.parsed,
        unknown: summary.unknown + databaseSummary.unknown,
        total: summary.total + databaseSummary.total,
      }),
      {
        scheduled: 0,
        in_progress: 0,
        parsed: 0,
        unknown: 0,
        total: 0,
      },
    ),
  };
}

function getRequestedSections(sections?: OverviewSection[]) {
  return new Set(sections ?? []);
}

export function createNavigationToolHandlers(analyzerApi: AnalyzerApi) {
  const fetchPackageByHash = async (hash: string) => {
    const hashLookup = await analyzerApi.getApi<Record<string, unknown>>(
      `/api/packages/hash/${encodeURIComponent(hash)}`,
    );
    const packageId = hashLookup.packageId ?? hashLookup.id ?? null;
    const resolvedPackageId =
      typeof packageId === "string" && packageId.trim().length > 0
        ? packageId
        : null;
    const item = resolvedPackageId
      ? await analyzerApi.getApi<Record<string, unknown>>(
          `/api/packages/${encodeURIComponent(resolvedPackageId)}`,
        )
      : null;

    return {
      hash_lookup: hashLookup,
      resolved_package_id: resolvedPackageId,
      item,
    };
  };

  return {
    analyzer_list_accounts: async (args: {
      limit?: number;
    }): Promise<McpToolResponse> => {
      const accounts =
        await analyzerApi.getApi<Array<Record<string, unknown>>>(
          "/api/accounts",
        );

      return toToolResponse(truncateItems(accounts, args.limit ?? 100));
    },

    analyzer_search_accounts: async (args: {
      query: string;
      limit?: number;
    }): Promise<McpToolResponse> => {
      const items = await analyzerApi.postApi<Array<Record<string, unknown>>>(
        "/api/accounts/search/query",
        {
          query: args.query,
        },
      );

      return toToolResponse(truncateItems(items, args.limit ?? 100));
    },

    analyzer_get_account: async (args: {
      account_id: string;
    }): Promise<McpToolResponse> => {
      const item = await analyzerApi.getApi<Record<string, unknown> | null>(
        `/api/accounts/${encodeURIComponent(args.account_id)}`,
      );

      return toToolResponse({ item });
    },

    analyzer_list_clusters: async (args: {
      account_id?: string;
      query?: string;
      limit?: number;
    }): Promise<McpToolResponse> => {
      const clusters =
        await analyzerApi.getApi<Array<Record<string, unknown>>>(
          "/api/clusters",
        );
      const items = clusters.filter(
        (cluster) =>
          (!args.account_id ||
            String(cluster.accountId ?? cluster.account_id ?? "") ===
              args.account_id) &&
          (!args.query ||
            matchesSubstring(cluster.name, args.query) ||
            matchesSubstring(cluster.accountId, args.query) ||
            matchesSubstring(cluster.account_id, args.query)),
      );

      return toToolResponse(truncateItems(items, args.limit ?? 100));
    },

    analyzer_get_cluster: async (args: {
      account_id: string;
      cluster_name: string;
    }): Promise<McpToolResponse> => {
      const item = await analyzerApi.getApi<Record<string, unknown> | null>(
        `/api/clusters/${encodeURIComponent(args.account_id)}/${encodeURIComponent(args.cluster_name)}`,
      );

      return toToolResponse({ item });
    },

    analyzer_list_packages: async (args: {
      account_id?: string;
      cluster_query?: string;
      package_query?: string;
      status?: string;
      user_id?: string;
      limit?: number;
    }): Promise<McpToolResponse> => {
      const packages =
        await analyzerApi.getApi<Array<Record<string, unknown>>>(
          "/api/packages",
        );
      const items = packages
        .filter(
          (pkg) =>
            (!args.account_id ||
              String(pkg.accountId ?? pkg.account_id ?? "") ===
                args.account_id) &&
            (!args.status || String(pkg.status ?? "") === args.status) &&
            (!args.user_id ||
              String(pkg.userId ?? pkg.user_id ?? "") === args.user_id) &&
            matchesSubstring(pkg.cluster, args.cluster_query) &&
            (!args.package_query ||
              matchesSubstring(pkg.id, args.package_query) ||
              matchesSubstring(pkg.name, args.package_query) ||
              matchesSubstring(pkg.cluster, args.package_query) ||
              matchesSubstring(pkg.hash, args.package_query)),
        )
        .sort((left, right) =>
          String(right.created ?? "").localeCompare(String(left.created ?? "")),
        );

      return toToolResponse(truncateItems(items, args.limit ?? 100));
    },

    analyzer_get_package_by_hash: async (args: {
      hash: string;
    }): Promise<McpToolResponse> => {
      const resolved = await fetchPackageByHash(args.hash);
      if (resolved.item) {
        return toToolResponse(resolved);
      }

      try {
        const item = await analyzerApi.getApi<Record<string, unknown> | null>(
          `/api/packages/${encodeURIComponent(args.hash)}`,
        );

        return toToolResponse({
          ...resolved,
          item,
          matched_by: item ? "package_id_fallback" : null,
          resolved_package_id:
            typeof item?.id === "string" ? item.id : args.hash,
        });
      } catch (error) {
        return toToolResponse(resolved);
      }
    },

    analyzer_get_package: async (args: {
      package_id: string;
    }): Promise<McpToolResponse> => {
      const item = await analyzerApi.getApi<Record<string, unknown> | null>(
        `/api/packages/${encodeURIComponent(args.package_id)}`,
      );

      return toToolResponse({ item });
    },

    analyzer_resolve_package: async (args: {
      reference: string;
    }): Promise<McpToolResponse> => {
      try {
        const item = await analyzerApi.getApi<Record<string, unknown> | null>(
          `/api/packages/${encodeURIComponent(args.reference)}`,
        );

        return toToolResponse({
          item,
          matched_by: "package_id",
          reference: args.reference,
        });
      } catch (error) {
        const resolved = await fetchPackageByHash(args.reference);

        return toToolResponse({
          ...resolved,
          matched_by: resolved.item ? "hash" : null,
          reference: args.reference,
        });
      }
    },

    analyzer_get_package_messages: async (args: {
      package_id: string;
      limit?: number;
    }): Promise<McpToolResponse> => {
      const messages = await analyzerApi.getApi<Array<Record<string, unknown>>>(
        `/api/packages/${encodeURIComponent(args.package_id)}/messages`,
      );

      return toToolResponse(truncateItems(messages, args.limit ?? 100));
    },

    analyzer_get_cluster_packages: async (args: {
      account_id: string;
      cluster_name: string;
      include_deleted?: boolean;
      limit?: number;
    }): Promise<McpToolResponse> => {
      const packages = (await analyzerApi.getApi<
        Array<Record<string, unknown>>
      >(
        `/api/clusters/${encodeURIComponent(args.account_id)}/${encodeURIComponent(args.cluster_name)}/packages`,
      )) as Array<Record<string, unknown>>;

      const deletedPackages = args.include_deleted
        ? (
            (await analyzerApi.getApi<Array<Record<string, unknown>>>(
              `/api/clusters/${encodeURIComponent(args.account_id)}/${encodeURIComponent(args.cluster_name)}/packages/deleted`,
            )) as Array<Record<string, unknown>>
          ).map((pkg) => ({
            ...pkg,
            deleted: pkg.deleted ?? true,
          }))
        : [];

      const items = packages
        .concat(deletedPackages)
        .sort((left, right) =>
          String(right.created ?? "").localeCompare(String(left.created ?? "")),
        );
      const limit = args.limit ?? 100;

      return toToolResponse(truncateItems(items, limit));
    },

    analyzer_get_latest_cluster_package: async (args: {
      account_id: string;
      cluster_name: string;
    }): Promise<McpToolResponse> => {
      const item = await analyzerApi.getApi<Record<string, unknown> | null>(
        `/api/clusters/${encodeURIComponent(args.account_id)}/${encodeURIComponent(args.cluster_name)}/packages/latest`,
      );

      return toToolResponse({ item });
    },

    analyzer_get_package_overview: async (args: {
      package_id: string;
      include_sections?: OverviewSection[];
    }): Promise<McpToolResponse> => {
      const requestedSections = getRequestedSections(args.include_sections);
      const [
        pkg,
        cluster,
        databases,
        nodes,
        tasks,
        alerts,
        parserStatus,
        healthCheckStatus,
      ] = await Promise.all([
        analyzerApi.getApi<Record<string, unknown>>(
          `/api/packages/${encodeURIComponent(args.package_id)}`,
        ),
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
          `/api/data/${encodeURIComponent(args.package_id)}/tasks`,
        ),
        analyzerApi.getApi<Array<Record<string, unknown>>>(
          `/api/data/${encodeURIComponent(args.package_id)}/alerts`,
          {
            sources: ["cluster", "node", "bdb", "BDB"],
            status: "active",
          },
        ),
        analyzerApi.getApi<Record<string, number>>(
          `/api/log/${encodeURIComponent(args.package_id)}`,
        ),
        analyzerApi.getApi<Array<Record<string, number>>>(
          `/api/health-check/${encodeURIComponent(args.package_id)}`,
        ),
      ]);

      const details: Record<string, unknown> = {};
      if (requestedSections.has("cluster")) {
        details.cluster = cluster;
      }
      if (requestedSections.has("databases")) {
        details.databases = databases;
      }
      if (requestedSections.has("nodes")) {
        details.nodes = nodes;
      }
      if (requestedSections.has("tasks")) {
        details.tasks = tasks;
      }
      if (requestedSections.has("alerts")) {
        details.alerts = alerts;
      }
      if (requestedSections.has("health_checks")) {
        details.health_checks = healthCheckStatus;
      }

      return toToolResponse({
        summary: {
          package: {
            id: pkg.id,
            name: pkg.name,
            account_id: pkg.accountId,
            cluster_name: pkg.cluster,
            created: pkg.created,
          },
          counts: {
            databases: databases.length,
            nodes: nodes.length,
            tasks: tasks.length,
            active_alerts: alerts.length,
          },
          parser_status: summarizeProcessStatus(parserStatus),
          health_check_status: summarizeHealthCheckStatus(healthCheckStatus),
        },
        details,
        related_ids: {
          package_id: pkg.id,
          account_id: pkg.accountId,
          cluster_name: pkg.cluster,
          database_ids: databases
            .map(getEntityId)
            .filter((id): id is number | string => id !== undefined),
          node_ids: nodes
            .map(getEntityId)
            .filter((id): id is number | string => id !== undefined),
        },
      });
    },
  };
}

export function registerNavigationTools(
  server: McpServer,
  analyzerApi: AnalyzerApi,
) {
  const handlers = createNavigationToolHandlers(analyzerApi);

  server.registerTool(
    "analyzer_list_accounts",
    {
      description: "List known Analyzer accounts.",
      inputSchema: {
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_list_accounts,
  );

  server.registerTool(
    "analyzer_search_accounts",
    {
      description: "Search Analyzer accounts by query string.",
      inputSchema: {
        query: z.string().min(1),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_search_accounts,
  );

  server.registerTool(
    "analyzer_get_account",
    {
      description: "Fetch one Analyzer account by exact account_id.",
      inputSchema: {
        account_id: z.string(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_account,
  );

  server.registerTool(
    "analyzer_list_clusters",
    {
      description:
        "List Analyzer clusters, with optional account filtering and substring matching.",
      inputSchema: {
        account_id: z.string().optional(),
        query: z.string().optional(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_list_clusters,
  );

  server.registerTool(
    "analyzer_get_cluster",
    {
      description: "Fetch one cluster by exact account_id and cluster_name.",
      inputSchema: {
        account_id: z.string(),
        cluster_name: z.string(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_cluster,
  );

  server.registerTool(
    "analyzer_list_packages",
    {
      description:
        "List packages globally, with optional MCP-side filtering by account, cluster substring, package substring, status, or user.",
      inputSchema: {
        account_id: z.string().optional(),
        cluster_query: z.string().optional(),
        package_query: z.string().optional(),
        status: z.string().optional(),
        user_id: z.string().optional(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_list_packages,
  );

  server.registerTool(
    "analyzer_get_package_by_hash",
    {
      description:
        "Resolve a package hash to a package id and return the package object. Use this only when the user explicitly provides a package hash field.",
      inputSchema: {
        hash: z.string().min(1),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_package_by_hash,
  );

  server.registerTool(
    "analyzer_get_package",
    {
      description:
        "Fetch one package by exact package_id. Prefer this when the identifier came from analyzer_list_packages, analyzer_get_cluster_packages, or Analyzer UI package inventory.",
      inputSchema: {
        package_id: z.string(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_package,
  );

  server.registerTool(
    "analyzer_resolve_package",
    {
      description:
        "Resolve a package reference when you do not know whether it is an Analyzer package_id or a package hash. This tries exact package_id first, then hash lookup.",
      inputSchema: {
        reference: z.string().min(1),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_resolve_package,
  );

  server.registerTool(
    "analyzer_get_package_messages",
    {
      description: "Fetch package processing and analysis messages.",
      inputSchema: {
        package_id: z.string(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_package_messages,
  );

  server.registerTool(
    "analyzer_get_cluster_packages",
    {
      description:
        "List packages for one cluster so an agent can move across package history.",
      inputSchema: {
        account_id: z.string(),
        cluster_name: z.string(),
        include_deleted: z.boolean().optional(),
        limit: z.number().int().positive().max(1000).optional(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_cluster_packages,
  );

  server.registerTool(
    "analyzer_get_latest_cluster_package",
    {
      description: "Fetch the latest package for one cluster.",
      inputSchema: {
        account_id: z.string(),
        cluster_name: z.string(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_latest_cluster_package,
  );

  server.registerTool(
    "analyzer_get_package_overview",
    {
      description:
        "Return the main agent entry point for a single support package.",
      inputSchema: {
        package_id: z.string(),
        include_sections: z.array(overviewSectionSchema).optional(),
      },
      annotations: {
        readOnlyHint: true,
      },
    },
    handlers.analyzer_get_package_overview,
  );
}
