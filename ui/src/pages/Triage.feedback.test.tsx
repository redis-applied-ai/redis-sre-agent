import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  submitFeedback: vi.fn(),
}));

vi.mock("../services/sreAgentApi", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../services/sreAgentApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      submitFeedback: mocks.submitFeedback,
    },
  };
});

import { FeedbackButtons } from "./Triage";

const feedbackRecord = (verdict: "up" | "down" | "withdrawn") => ({
  task_id: "task-1",
  verdict,
  comment: null,
  created_at: "2026-06-04T18:00:00Z",
  updated_at: "2026-06-04T18:00:00Z",
});

describe("FeedbackButtons", () => {
  beforeEach(() => {
    mocks.submitFeedback.mockReset();
  });

  it("renders persisted feedback as the active state", () => {
    render(
      <FeedbackButtons
        taskId="task-1"
        initialVerdict="down"
        onError={vi.fn()}
      />,
    );

    expect(screen.getByTestId("feedback-up")).toHaveAttribute(
      "data-active",
      "false",
    );
    expect(screen.getByTestId("feedback-down")).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("submits thumbs up with keyboard activation", async () => {
    const user = userEvent.setup();
    mocks.submitFeedback.mockResolvedValueOnce(feedbackRecord("up"));

    render(
      <FeedbackButtons taskId="task-1" initialVerdict={null} onError={vi.fn()} />,
    );

    screen.getByTestId("feedback-up").focus();
    await user.keyboard("{Enter}");

    expect(mocks.submitFeedback).toHaveBeenCalledWith("task-1", "up");
    await waitFor(() => {
      expect(screen.getByTestId("feedback-up")).toHaveAttribute(
        "data-active",
        "true",
      );
    });
  });

  it("clicking the active verdict withdraws feedback", async () => {
    const user = userEvent.setup();
    mocks.submitFeedback.mockResolvedValueOnce(feedbackRecord("withdrawn"));

    render(
      <FeedbackButtons
        taskId="task-1"
        initialVerdict="up"
        onError={vi.fn()}
      />,
    );

    await user.click(screen.getByTestId("feedback-up"));

    expect(mocks.submitFeedback).toHaveBeenCalledWith("task-1", "withdrawn");
    await waitFor(() => {
      expect(screen.getByTestId("feedback-up")).toHaveAttribute(
        "data-active",
        "false",
      );
    });
  });

  it("disables both buttons while a submission is pending", async () => {
    const user = userEvent.setup();
    let resolveSubmit: (record: ReturnType<typeof feedbackRecord>) => void;
    const pending = new Promise<ReturnType<typeof feedbackRecord>>((resolve) => {
      resolveSubmit = resolve;
    });
    mocks.submitFeedback.mockReturnValueOnce(pending);

    render(
      <FeedbackButtons taskId="task-1" initialVerdict={null} onError={vi.fn()} />,
    );

    await user.click(screen.getByTestId("feedback-down"));

    expect(screen.getByTestId("feedback-up")).toBeDisabled();
    expect(screen.getByTestId("feedback-down")).toBeDisabled();

    await user.click(screen.getByTestId("feedback-up"));
    expect(mocks.submitFeedback).toHaveBeenCalledTimes(1);

    resolveSubmit!(feedbackRecord("down"));
    await waitFor(() => {
      expect(screen.getByTestId("feedback-down")).not.toBeDisabled();
    });
  });

  it("rolls back optimistic state and reports submit errors", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();
    mocks.submitFeedback.mockRejectedValueOnce(new Error("Redis unavailable"));

    render(
      <FeedbackButtons
        taskId="task-1"
        initialVerdict="down"
        onError={onError}
      />,
    );

    await user.click(screen.getByTestId("feedback-up"));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(
        "Failed to submit feedback: Redis unavailable",
      );
      expect(screen.getByTestId("feedback-down")).toHaveAttribute(
        "data-active",
        "true",
      );
    });
  });
});
