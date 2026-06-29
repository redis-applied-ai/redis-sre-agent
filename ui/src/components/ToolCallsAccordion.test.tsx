import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ToolCallsAccordion from "./ToolCallsAccordion";

describe("ToolCallsAccordion", () => {
  it("renders nothing when there are no tool calls or tool updates", () => {
    render(<ToolCallsAccordion toolCalls={[]} updates={[]} />);

    expect(screen.queryByTestId("tool-calls-accordion")).toBeNull();
  });

  it("normalizes tool-call updates and renders failed long outputs", async () => {
    const user = userEvent.setup();
    const longOutput = `warning: ${"memory pressure ".repeat(80)}`;

    render(
      <ToolCallsAccordion
        updates={[
          {
            timestamp: "2026-06-29T18:00:00Z",
            type: "tool_call",
            message: "Executing tool: redis_sre_123abc_get_metric_window",
            metadata: {
              status: "failed",
              tool_args: { metric: "instantaneous_ops_per_sec" },
              result: {
                status: "failed",
                error: longOutput,
              },
            },
          },
        ]}
      />,
    );

    const accordion = screen.getByTestId("tool-calls-accordion");
    expect(accordion).not.toHaveAttribute("open");
    expect(within(accordion).getByText("Tool calls")).toBeInTheDocument();
    expect(within(accordion).getByText("1")).toBeInTheDocument();

    await user.click(within(accordion).getByText("Tool calls"));
    expect(accordion).toHaveAttribute("open");

    const toolCall = within(accordion).getByTestId("tool-call-item");
    expect(within(toolCall).getByText("get_metric_window")).toBeInTheDocument();
    expect(within(toolCall).getByText("failed")).toBeInTheDocument();

    await user.click(within(toolCall).getByText("get_metric_window"));
    expect(toolCall).toHaveAttribute("open");
    expect(
      within(toolCall).getByText(/instantaneous_ops_per_sec/),
    ).toBeInTheDocument();
    expect(within(toolCall).getByText(/memory pressure/)).toBeInTheDocument();
  });
});
