import { createNavigationToolHandlers } from "../../src/navigation-tools";
import { AnalyzerApi } from "../../src/types";

describe("createNavigationToolHandlers", () => {
  function createApi(): jest.Mocked<AnalyzerApi> {
    return {
      getApi: jest.fn(),
      getPrivate: jest.fn(),
      postApi: jest.fn(),
    };
  }

  it("lists cluster packages newest first and composes deleted packages when requested", async () => {
    const api = createApi();
    api.getApi.mockImplementation(async (path: string) => {
      if (path.endsWith("/packages/deleted")) {
        return [{ id: "pkg-0", created: "2024-01-01T00:00:00.000Z" }];
      }

      return [
        { id: "pkg-1", created: "2024-02-01T00:00:00.000Z" },
        { id: "pkg-2", created: "2024-03-01T00:00:00.000Z" },
      ];
    });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_cluster_packages({
      account_id: "123",
      cluster_name: "cluster-a",
      include_deleted: true,
      limit: 2,
    });

    expect(api.getApi).toHaveBeenNthCalledWith(
      1,
      "/api/clusters/123/cluster-a/packages",
    );
    expect(api.getApi).toHaveBeenNthCalledWith(
      2,
      "/api/clusters/123/cluster-a/packages/deleted",
    );
    expect(result.structuredContent).toEqual({
      count: 3,
      items: [
        { created: "2024-03-01T00:00:00.000Z", id: "pkg-2" },
        { created: "2024-02-01T00:00:00.000Z", id: "pkg-1" },
      ],
      truncated: true,
    });
  });

  it("returns the latest package for a cluster", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue({
      id: "pkg-latest",
      created: "2024-03-01T00:00:00.000Z",
    });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_latest_cluster_package({
      account_id: "123",
      cluster_name: "cluster-a",
    });

    expect(api.getApi).toHaveBeenCalledWith(
      "/api/clusters/123/cluster-a/packages/latest",
    );
    expect(result.structuredContent).toEqual({
      item: { created: "2024-03-01T00:00:00.000Z", id: "pkg-latest" },
    });
  });

  it("builds a compact package overview and expands requested sections", async () => {
    const api = createApi();
    api.getApi.mockImplementation(
      async (path: string, params?: Record<string, unknown>) => {
        switch (path) {
          case "/api/packages/pkg-1":
            return {
              id: "pkg-1",
              name: "support-package.tar.gz",
              accountId: "123",
              cluster: "cluster-a",
              created: "2024-03-01T00:00:00.000Z",
            };
          case "/api/data/pkg-1/cluster":
            return { name: "cluster-a", softwareVersion: "7.2.4" };
          case "/api/data/pkg-1/bdbs":
            return [{ uid: 11 }, { uid: 12 }];
          case "/api/data/pkg-1/nodes":
            return [{ uid: 21 }, { uid: 22 }, { uid: 23 }];
          case "/api/data/pkg-1/tasks":
            return [{ uid: "task-1" }];
          case "/api/data/pkg-1/alerts":
            expect(params).toEqual({
              sources: ["cluster", "node", "bdb", "BDB"],
              status: "active",
            });
            return [{ id: "alert-1" }, { id: "alert-2" }];
          case "/api/log/pkg-1":
            return {
              rule_a: 0,
              rule_b: -1,
            };
          case "/api/health-check/pkg-1":
            return [{ cluster_sm: 0 }, { ts_gap: -2 }, { log_scan: -1 }];
          default:
            throw new Error(`Unexpected path: ${path}`);
        }
      },
    );

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_package_overview({
      package_id: "pkg-1",
      include_sections: ["cluster", "alerts", "health_checks"],
    });

    expect(result.structuredContent).toEqual({
      details: {
        alerts: [{ id: "alert-1" }, { id: "alert-2" }],
        cluster: { name: "cluster-a", softwareVersion: "7.2.4" },
        health_checks: [{ cluster_sm: 0 }, { ts_gap: -2 }, { log_scan: -1 }],
      },
      related_ids: {
        account_id: "123",
        cluster_name: "cluster-a",
        database_ids: [11, 12],
        node_ids: [21, 22, 23],
        package_id: "pkg-1",
      },
      summary: {
        counts: {
          active_alerts: 2,
          databases: 2,
          nodes: 3,
          tasks: 1,
        },
        health_check_status: {
          by_database: {
            data: {
              parsed: 1,
              scheduled: 0,
              in_progress: 0,
              unknown: 0,
              total: 1,
            },
            log: {
              parsed: 0,
              scheduled: 0,
              in_progress: 1,
              unknown: 0,
              total: 1,
            },
            timeseries: {
              parsed: 0,
              scheduled: 1,
              in_progress: 0,
              unknown: 0,
              total: 1,
            },
          },
          total: {
            parsed: 1,
            scheduled: 1,
            in_progress: 1,
            unknown: 0,
            total: 3,
          },
        },
        package: {
          account_id: "123",
          cluster_name: "cluster-a",
          created: "2024-03-01T00:00:00.000Z",
          id: "pkg-1",
          name: "support-package.tar.gz",
        },
        parser_status: {
          in_progress: 1,
          parsed: 1,
          scheduled: 0,
          total: 2,
          unknown: 0,
        },
      },
    });
  });

  it("lists accounts with MCP-side truncation", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { id: "200", name: "Beta Corp" },
      { id: "100", name: "Acme" },
    ]);

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_list_accounts({
      limit: 1,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/accounts");
    expect(result.structuredContent).toEqual({
      count: 2,
      items: [{ id: "200", name: "Beta Corp" }],
      truncated: true,
    });
  });

  it("searches accounts through the backend search endpoint", async () => {
    const api = createApi();
    api.postApi.mockResolvedValue([
      {
        id: "100",
        index: "accounts",
        score: "1",
        value: { id: "100", name: "Acme" },
      },
    ]);

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_search_accounts({
      query: "acme",
      limit: 10,
    });

    expect(api.postApi).toHaveBeenCalledWith("/api/accounts/search/query", {
      query: "acme",
    });
    expect(result.structuredContent).toEqual({
      count: 1,
      items: [
        {
          id: "100",
          index: "accounts",
          score: "1",
          value: { id: "100", name: "Acme" },
        },
      ],
      truncated: false,
    });
  });

  it("fetches one account directly", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue({ id: "100", name: "Acme" });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_account({
      account_id: "100",
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/accounts/100");
    expect(result.structuredContent).toEqual({
      item: { id: "100", name: "Acme" },
    });
  });

  it("lists and filters clusters with MCP-side substring matching", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { accountId: "100", name: "alpha-prod" },
      { accountId: "200", name: "beta-stage" },
      { accountId: "100", name: "alpha-dev" },
    ]);

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_list_clusters({
      account_id: "100",
      query: "prod",
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/clusters");
    expect(result.structuredContent).toEqual({
      count: 1,
      items: [{ accountId: "100", name: "alpha-prod" }],
      truncated: false,
    });
  });

  it("fetches a cluster directly", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue({
      accountId: "100",
      name: "alpha-prod",
    });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_cluster({
      account_id: "100",
      cluster_name: "alpha-prod",
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/clusters/100/alpha-prod");
    expect(result.structuredContent).toEqual({
      item: { accountId: "100", name: "alpha-prod" },
    });
  });

  it("lists and filters packages globally", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      {
        id: "pkg-1",
        name: "support-a.tar.gz",
        accountId: "100",
        cluster: "alpha-prod-1",
        created: "2024-02-01T00:00:00.000Z",
        status: "active",
      },
      {
        id: "pkg-2",
        name: "support-b.tar.gz",
        accountId: "200",
        cluster: "beta-stage-1",
        created: "2024-03-01T00:00:00.000Z",
        status: "deleted",
      },
      {
        id: "pkg-3",
        name: "support-c.tar.gz",
        accountId: "100",
        cluster: "alpha-prod-2",
        created: "2024-04-01T00:00:00.000Z",
        status: "active",
      },
    ]);

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_list_packages({
      account_id: "100",
      cluster_query: "prod",
      status: "active",
      limit: 1,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/packages");
    expect(result.structuredContent).toEqual({
      count: 2,
      items: [
        {
          accountId: "100",
          cluster: "alpha-prod-2",
          created: "2024-04-01T00:00:00.000Z",
          id: "pkg-3",
          name: "support-c.tar.gz",
          status: "active",
        },
      ],
      truncated: true,
    });
  });

  it("resolves a package by hash and returns the package object", async () => {
    const api = createApi();
    api.getApi.mockImplementation(async (path: string) => {
      if (path === "/api/packages/hash/hash-123") {
        return { packageId: "pkg-1" };
      }

      if (path === "/api/packages/pkg-1") {
        return { id: "pkg-1", name: "support.tar.gz" };
      }

      throw new Error(`Unexpected path: ${path}`);
    });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_package_by_hash({
      hash: "hash-123",
    });

    expect(api.getApi).toHaveBeenNthCalledWith(
      1,
      "/api/packages/hash/hash-123",
    );
    expect(api.getApi).toHaveBeenNthCalledWith(2, "/api/packages/pkg-1");
    expect(result.structuredContent).toEqual({
      hash_lookup: { packageId: "pkg-1" },
      resolved_package_id: "pkg-1",
      item: { id: "pkg-1", name: "support.tar.gz" },
    });
  });

  it("tolerates a package id passed to the hash tool by falling back to package lookup", async () => {
    const api = createApi();
    api.getApi.mockImplementation(async (path: string) => {
      if (path === "/api/packages/hash/pkg-1") {
        return { packageId: null };
      }

      if (path === "/api/packages/pkg-1") {
        return { id: "pkg-1", name: "support.tar.gz" };
      }

      throw new Error(`Unexpected path: ${path}`);
    });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_package_by_hash({
      hash: "pkg-1",
    });

    expect(api.getApi).toHaveBeenNthCalledWith(1, "/api/packages/hash/pkg-1");
    expect(api.getApi).toHaveBeenNthCalledWith(2, "/api/packages/pkg-1");
    expect(result.structuredContent).toEqual({
      hash_lookup: { packageId: null },
      item: { id: "pkg-1", name: "support.tar.gz" },
      matched_by: "package_id_fallback",
      resolved_package_id: "pkg-1",
    });
  });

  it("resolves a package reference from an exact package id", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue({ id: "pkg-1", name: "support.tar.gz" });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_resolve_package({
      reference: "pkg-1",
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/packages/pkg-1");
    expect(result.structuredContent).toEqual({
      item: { id: "pkg-1", name: "support.tar.gz" },
      matched_by: "package_id",
      reference: "pkg-1",
    });
  });

  it("falls back to hash lookup when exact package id lookup fails", async () => {
    const api = createApi();
    api.getApi.mockImplementation(async (path: string) => {
      if (path === "/api/packages/pkg-hash") {
        throw new Error("Package [pkg-hash]: not found");
      }

      if (path === "/api/packages/hash/pkg-hash") {
        return { packageId: "pkg-1" };
      }

      if (path === "/api/packages/pkg-1") {
        return { id: "pkg-1", name: "support.tar.gz" };
      }

      throw new Error(`Unexpected path: ${path}`);
    });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_resolve_package({
      reference: "pkg-hash",
    });

    expect(api.getApi).toHaveBeenNthCalledWith(1, "/api/packages/pkg-hash");
    expect(api.getApi).toHaveBeenNthCalledWith(
      2,
      "/api/packages/hash/pkg-hash",
    );
    expect(api.getApi).toHaveBeenNthCalledWith(3, "/api/packages/pkg-1");
    expect(result.structuredContent).toEqual({
      hash_lookup: { packageId: "pkg-1" },
      item: { id: "pkg-1", name: "support.tar.gz" },
      matched_by: "hash",
      reference: "pkg-hash",
      resolved_package_id: "pkg-1",
    });
  });

  it("returns an unresolved package response when neither id nor hash match", async () => {
    const api = createApi();
    api.getApi.mockImplementation(async (path: string) => {
      if (path === "/api/packages/missing-ref") {
        throw new Error("Package [missing-ref]: not found");
      }

      if (path === "/api/packages/hash/missing-ref") {
        return { packageId: null };
      }

      throw new Error(`Unexpected path: ${path}`);
    });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_resolve_package({
      reference: "missing-ref",
    });

    expect(result.structuredContent).toEqual({
      hash_lookup: { packageId: null },
      item: null,
      matched_by: null,
      reference: "missing-ref",
      resolved_package_id: null,
    });
  });

  it("fetches one package directly", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue({ id: "pkg-1", name: "support.tar.gz" });

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_package({
      package_id: "pkg-1",
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/packages/pkg-1");
    expect(result.structuredContent).toEqual({
      item: { id: "pkg-1", name: "support.tar.gz" },
    });
  });

  it("returns package messages", async () => {
    const api = createApi();
    api.getApi.mockResolvedValue([
      { id: "msg-1", message: "parsed" },
      { id: "msg-2", message: "health checks complete" },
    ]);

    const handlers = createNavigationToolHandlers(api);
    const result = await handlers.analyzer_get_package_messages({
      package_id: "pkg-1",
      limit: 1,
    });

    expect(api.getApi).toHaveBeenCalledWith("/api/packages/pkg-1/messages");
    expect(result.structuredContent).toEqual({
      count: 2,
      items: [{ id: "msg-1", message: "parsed" }],
      truncated: true,
    });
  });
});
