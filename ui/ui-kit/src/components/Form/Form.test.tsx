import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Form } from "./Form";

describe("Form", () => {
  it("calls onChange once per field update", () => {
    const handleChange = vi.fn();

    render(
      <Form
        fields={[
          {
            name: "name",
            label: "Name",
            type: "text",
          },
        ]}
        initialData={{ name: "" }}
        onSubmit={() => {}}
        onChange={handleChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Alice" },
    });

    expect(handleChange).toHaveBeenCalledTimes(1);
    expect(handleChange).toHaveBeenCalledWith({ name: "Alice" });
  });
});
