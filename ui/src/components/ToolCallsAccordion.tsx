import type { TaskToolCall, TaskUpdate } from "../services/sreAgentApi";

interface ToolCallsAccordionProps {
  toolCalls?: TaskToolCall[] | null;
  updates?: TaskUpdate[] | null;
  className?: string;
}

const extractOperationName = (fullToolName: string): string => {
  const match = fullToolName.match(/_([0-9a-f]{6})_(.+)$/);
  return match ? match[2] : fullToolName;
};

const compactJson = (value: unknown) => {
  if (typeof value === "string") return value;

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const objectValue = (value: unknown): Record<string, any> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : {};

const parseToolNameFromMessage = (message: unknown) => {
  if (typeof message !== "string") return undefined;
  const match = message.match(/^Executing tool:\s*(.+)$/i);
  return match?.[1]?.trim() || undefined;
};

const toolCallName = (toolCall: TaskToolCall, index: number) => {
  const metadata = objectValue(toolCall.metadata);
  const nestedTool = objectValue(metadata.tool);
  const nestedToolCall = objectValue(metadata.tool_call || metadata.toolCall);
  const rawName =
    toolCall.name ||
    toolCall.tool_name ||
    toolCall.tool_key ||
    metadata.tool_name ||
    metadata.name ||
    metadata.tool_name_full ||
    nestedTool.name ||
    nestedToolCall.name ||
    parseToolNameFromMessage(toolCall.message) ||
    `Tool call ${index + 1}`;
  return extractOperationName(String(rawName));
};

const toolCallArgs = (toolCall: TaskToolCall) => {
  const metadata = objectValue(toolCall.metadata);
  const nestedTool = objectValue(metadata.tool);
  const nestedToolCall = objectValue(metadata.tool_call || metadata.toolCall);
  return (
    toolCall.args ||
    toolCall.tool_args ||
    toolCall.arguments ||
    toolCall.input ||
    metadata.tool_args ||
    metadata.args ||
    metadata.arguments ||
    nestedTool.args ||
    nestedToolCall.args ||
    nestedToolCall.arguments ||
    null
  );
};

const toolCallResult = (toolCall: TaskToolCall) => {
  const metadata = objectValue(toolCall.metadata);
  return (
    toolCall.result ||
    toolCall.data ||
    toolCall.output ||
    toolCall.response ||
    metadata.result ||
    null
  );
};

export const normalizeToolCalls = (
  toolCalls?: TaskToolCall[] | null,
  updates?: TaskUpdate[] | null,
) => {
  if (Array.isArray(toolCalls) && toolCalls.length > 0) {
    return toolCalls;
  }

  if (!Array.isArray(updates)) {
    return [];
  }

  return updates
    .filter((update) => update.type === "tool_call")
    .map((update, index) => {
      const metadata = objectValue(update.metadata);
      const nestedTool = objectValue(metadata.tool);
      const nestedToolCall = objectValue(
        metadata.tool_call || metadata.toolCall,
      );
      const result = metadata.result;
      const resultObject = objectValue(result);

      return {
        id: `${update.timestamp || "tool"}-${index}`,
        name:
          metadata.tool_name ||
          metadata.name ||
          metadata.tool_name_full ||
          nestedTool.name ||
          nestedToolCall.name ||
          parseToolNameFromMessage(update.message),
        args:
          metadata.tool_args ||
          metadata.args ||
          metadata.arguments ||
          nestedTool.args ||
          nestedToolCall.args ||
          nestedToolCall.arguments,
        status: metadata.status || resultObject.status,
        message: update.message,
        result,
        timestamp: update.timestamp,
      };
    });
};

const ToolCallsAccordion = ({
  toolCalls,
  updates,
  className = "",
}: ToolCallsAccordionProps) => {
  const normalizedToolCalls = normalizeToolCalls(toolCalls, updates);

  if (normalizedToolCalls.length === 0) {
    return null;
  }

  return (
    <details
      data-testid="tool-calls-accordion"
      className={`tool-calls-accordion w-full max-w-3xl overflow-hidden rounded-redis-sm text-redis-sm ${className}`}
    >
      <summary className="tool-calls-accordion-summary flex cursor-pointer items-center gap-2 px-3 py-2 text-left font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-redis-blue-03">
        <span
          aria-hidden="true"
          className="accordion-chevron flex h-3 w-3 flex-shrink-0 items-center justify-center"
        >
          <span className="h-1.5 w-1.5 border-b border-r border-current" />
        </span>
        <span>Tool calls</span>
        <span className="tool-calls-count">{normalizedToolCalls.length}</span>
      </summary>
      <div className="tool-calls-accordion-body px-3 py-2 pl-8">
        <div className="space-y-2">
          {normalizedToolCalls.map((toolCall, index) => {
            const name = toolCallName(toolCall, index);
            const args = toolCallArgs(toolCall);
            const result = toolCallResult(toolCall);
            const status = toolCall.status ? String(toolCall.status) : "";

            return (
              <details
                key={toolCall.id || `${name}-${index}`}
                data-testid="tool-call-item"
                className="tool-call-item rounded-redis-sm"
              >
                <summary className="tool-call-item-summary flex cursor-pointer items-center gap-2 px-2 py-1.5 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-redis-blue-03">
                  <span
                    aria-hidden="true"
                    className="accordion-chevron flex h-3 w-3 flex-shrink-0 items-center justify-center"
                  >
                    <span className="h-1.5 w-1.5 border-b border-r border-current" />
                  </span>
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {name}
                  </span>
                  {status && (
                    <span className="tool-call-status flex-shrink-0">
                      {status}
                    </span>
                  )}
                </summary>
                <div className="tool-call-detail space-y-2 px-2 pb-2 pl-7">
                  {args && (
                    <div>
                      <div className="tool-call-detail-label">Arguments</div>
                      <pre>{compactJson(args)}</pre>
                    </div>
                  )}
                  {result && (
                    <div>
                      <div className="tool-call-detail-label">Result</div>
                      <pre>{compactJson(result)}</pre>
                    </div>
                  )}
                  {!args && !result && toolCall.message && (
                    <p>{toolCall.message}</p>
                  )}
                </div>
              </details>
            );
          })}
        </div>
      </div>
    </details>
  );
};

export default ToolCallsAccordion;
