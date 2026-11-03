// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Field, Input } from "./form";

afterEach(cleanup);

describe("Field", () => {
  it("labels the control itself when a button sits beside it", () => {
    render(
      <Field label="Coupon code" error="This coupon is not valid or has expired." trailing={<button>Apply</button>}>
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText("Coupon code");
    expect(input.tagName).toBe("INPUT");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const error = document.getElementById(input.getAttribute("aria-describedby") ?? "");
    expect(error?.textContent).toBe("This coupon is not valid or has expired.");
    expect(screen.getByRole("button", { name: "Apply" })).toBeTruthy();
  });

  it("without a button, the child is the control as before", () => {
    render(
      <Field label="City" hint="Where you live">
        <Input />
      </Field>,
    );
    expect(screen.getByLabelText("City").tagName).toBe("INPUT");
  });
});
