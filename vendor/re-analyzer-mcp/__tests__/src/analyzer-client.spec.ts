import { AxiosInstance } from "axios";
import { AnalyzerClient } from "../../src/analyzer-client";

describe("AnalyzerClient", () => {
  function createClient(request: jest.Mock) {
    return new AnalyzerClient(
      {
        analyzerBaseUrl: "https://analyzer.example.com",
        analyzerApiToken: "token-123",
        analyzerReportUser: "report-user",
        analyzerReportPassword: "report-password",
        requestTimeoutMs: 15000,
      },
      { request } as unknown as AxiosInstance,
    );
  }

  it("sends authenticated API GET requests", async () => {
    const request = jest.fn().mockResolvedValue({ data: [{ id: "pkg-1" }] });
    const client = createClient(request);

    await expect(client.getApi("/api/packages", { limit: 5 })).resolves.toEqual(
      [{ id: "pkg-1" }],
    );
    expect(request).toHaveBeenCalledWith({
      baseURL: "https://analyzer.example.com",
      headers: {
        Authorization: "Bearer token-123",
      },
      method: "GET",
      params: {
        limit: 5,
      },
      timeout: 15000,
      url: "/api/packages",
    });
  });

  it("sends authenticated API POST requests", async () => {
    const request = jest.fn().mockResolvedValue({ data: [{ id: "event-1" }] });
    const client = createClient(request);

    await expect(
      client.postApi("/api/data/pkg-1/events/search", { limit: 10 }),
    ).resolves.toEqual([{ id: "event-1" }]);
    expect(request).toHaveBeenCalledWith({
      baseURL: "https://analyzer.example.com",
      data: {
        limit: 10,
      },
      headers: {
        Authorization: "Bearer token-123",
      },
      method: "POST",
      timeout: 15000,
      url: "/api/data/pkg-1/events/search",
    });
  });

  it("sends authenticated private requests with report credentials", async () => {
    const request = jest.fn().mockResolvedValue({ data: { ok: true } });
    const client = createClient(request);

    await expect(client.getPrivate("/private/packages")).resolves.toEqual({
      ok: true,
    });
    expect(request).toHaveBeenCalledWith({
      baseURL: "https://analyzer.example.com",
      auth: {
        password: "report-password",
        username: "report-user",
      },
      headers: {
        Authorization: "Bearer token-123",
      },
      method: "GET",
      params: undefined,
      timeout: 15000,
      url: "/private/packages",
    });
  });

  it("rejects private requests without report credentials", async () => {
    const client = new AnalyzerClient({
      analyzerBaseUrl: "https://analyzer.example.com",
      analyzerApiToken: "token-123",
      analyzerReportPassword: undefined,
      analyzerReportUser: undefined,
      requestTimeoutMs: 15000,
    } as never);

    await expect(client.getPrivate("/private/packages")).rejects.toThrow(
      /report credentials/i,
    );
  });
});
