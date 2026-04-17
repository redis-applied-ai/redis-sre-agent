import { McpToolResponse } from "./types";

export const PROCESS_STATUS_LABELS = {
  "-2": "scheduled",
  "-1": "in_progress",
  "0": "parsed",
} as const;

export interface ProcessStatusSummary {
  scheduled: number;
  in_progress: number;
  parsed: number;
  unknown: number;
  total: number;
}

export function toToolResponse(
  payload: Record<string, unknown>,
): McpToolResponse {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(payload, null, 2),
      },
    ],
    structuredContent: payload,
  };
}

export function summarizeProcessStatus(
  statusMap: Record<string, number>,
): ProcessStatusSummary {
  return Object.values(statusMap).reduce<ProcessStatusSummary>(
    (summary, statusCode) => {
      const label =
        PROCESS_STATUS_LABELS[
          String(statusCode) as keyof typeof PROCESS_STATUS_LABELS
        ];

      if (!label) {
        summary.unknown += 1;
      } else {
        summary[label] += 1;
      }

      summary.total += 1;
      return summary;
    },
    {
      scheduled: 0,
      in_progress: 0,
      parsed: 0,
      unknown: 0,
      total: 0,
    },
  );
}

export function getEntityId(
  value: Record<string, unknown>,
): number | string | undefined {
  const keys = ["uid", "id", "bdbId", "nodeId"];

  for (const key of keys) {
    if (typeof value[key] === "number" || typeof value[key] === "string") {
      return value[key] as number | string;
    }
  }

  return undefined;
}

export function truncateItems<T>(items: T[], limit = 100) {
  return {
    items: items.slice(0, limit),
    count: items.length,
    truncated: items.length > limit,
  };
}
