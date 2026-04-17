import { loadConfig } from "../../src/config";

describe("loadConfig", () => {
  it("loads required configuration and applies the default timeout", () => {
    const config = loadConfig({
      ANALYZER_BASE_URL: "https://analyzer.example.com",
      ANALYZER_API_TOKEN: "token-123",
    });

    expect(config).toEqual({
      analyzerBaseUrl: "https://analyzer.example.com",
      analyzerApiToken: "token-123",
      analyzerReportPassword: undefined,
      analyzerReportUser: undefined,
      requestTimeoutMs: 30000,
    });
  });

  it("loads optional report credentials and timeout override", () => {
    const config = loadConfig({
      ANALYZER_BASE_URL: "https://analyzer.example.com",
      ANALYZER_API_TOKEN: "token-123",
      ANALYZER_REPORT_USER: "report-user",
      ANALYZER_REPORT_PASSWORD: "report-password",
      ANALYZER_TIMEOUT_MS: "15000",
    });

    expect(config.analyzerReportUser).toBe("report-user");
    expect(config.analyzerReportPassword).toBe("report-password");
    expect(config.requestTimeoutMs).toBe(15000);
  });

  it("rejects missing required configuration", () => {
    expect(() => loadConfig({})).toThrow(/ANALYZER_BASE_URL/i);
  });
});
