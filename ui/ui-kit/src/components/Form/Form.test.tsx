import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Form, type FormFieldConfig } from "./Form";

describe("Form", () => {
  it("emits the next form state once per field change", () => {
    const onChange = vi.fn();
    const fields: FormFieldConfig[] = [
      {
        name: "formType",
        label: "Form Type",
        type: "select",
        options: [
          { label: "User", value: "user" },
          { label: "Organization", value: "organization" },
        ],
      },
    ];

    render(
      <Form
        fields={fields}
        initialData={{ formType: "user" }}
        onChange={onChange}
        onSubmit={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText("Form Type"), {
      target: { value: "organization" },
    });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith({ formType: "organization" });
  });
});
