import { render, screen } from "@testing-library/react";
import MarkdownRenderer from "./MarkdownRenderer";

describe("MarkdownRenderer", () => {
  it("renders GitHub-flavored Markdown for chat and knowledge fragments", () => {
    render(
      <MarkdownRenderer
        content={`## Findings

- maxmemory is set
- eviction is active

| Metric | Value |
| --- | --- |
| used_memory | 12mb |

[Redis docs](https://redis.io/docs/latest/)`}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Findings" }),
    ).toBeInTheDocument();
    expect(screen.getByText("maxmemory is set")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Redis docs" })).toHaveAttribute(
      "target",
      "_blank",
    );
  });
});
