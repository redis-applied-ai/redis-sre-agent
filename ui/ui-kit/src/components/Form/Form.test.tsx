import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
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

  it("preserves queued field changes in the emitted form state", () => {
    const onChange = vi.fn();
    const fields: FormFieldConfig[] = [
      { name: "firstName", label: "First Name", type: "text" },
      { name: "lastName", label: "Last Name", type: "text" },
    ];

    render(
      <Form
        fields={fields}
        initialData={{ firstName: "", lastName: "" }}
        onChange={onChange}
        onSubmit={() => {}}
      />,
    );

    act(() => {
      fireEvent.change(screen.getByLabelText("First Name"), {
        target: { value: "Ada" },
      });
      fireEvent.change(screen.getByLabelText("Last Name"), {
        target: { value: "Lovelace" },
      });
    });

    expect(onChange).toHaveBeenLastCalledWith({
      firstName: "Ada",
      lastName: "Lovelace",
    });
  });
});
