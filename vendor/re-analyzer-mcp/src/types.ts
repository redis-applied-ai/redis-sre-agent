export interface AnalyzerConfig {
  analyzerBaseUrl: string;
  analyzerApiToken: string;
  analyzerReportUser?: string;
  analyzerReportPassword?: string;
  requestTimeoutMs: number;
}

export interface AnalyzerApi {
  getApi<T>(path: string, params?: Record<string, unknown>): Promise<T>;
  postApi<T>(path: string, data?: Record<string, unknown>): Promise<T>;
  getPrivate<T>(path: string, params?: Record<string, unknown>): Promise<T>;
}

export interface McpToolResponse {
  [key: string]: unknown;
  content: [{ type: "text"; text: string }];
  structuredContent: Record<string, unknown>;
}
