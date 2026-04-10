import { z } from "zod";
import { AnalyzerConfig } from "./types";

const envSchema = z.object({
  ANALYZER_BASE_URL: z.url(),
  ANALYZER_API_TOKEN: z.string().min(1),
  ANALYZER_REPORT_USER: z.string().min(1).optional(),
  ANALYZER_REPORT_PASSWORD: z.string().min(1).optional(),
  ANALYZER_TIMEOUT_MS: z.coerce.number().int().positive().default(30000),
});

export function loadConfig(
  env: Record<string, string | undefined> = process.env,
): AnalyzerConfig {
  const parsed = envSchema.parse(env);

  return {
    analyzerBaseUrl: parsed.ANALYZER_BASE_URL,
    analyzerApiToken: parsed.ANALYZER_API_TOKEN,
    analyzerReportUser: parsed.ANALYZER_REPORT_USER,
    analyzerReportPassword: parsed.ANALYZER_REPORT_PASSWORD,
    requestTimeoutMs: parsed.ANALYZER_TIMEOUT_MS,
  };
}
