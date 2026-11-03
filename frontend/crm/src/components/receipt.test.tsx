// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { StepOption } from "../api/types";
import { DecisionReceipt } from "./receipt";

afterEach(cleanup);

function option(action: StepOption["action"], p: number, profit: number, blocked: string | null = null): StepOption {
  return {
    action,
    label: "",
    blocked,
    discount: 0,
    cost: 0,
    p_convert: p,
    uplift: 0,
    expected_profit: profit,
    incremental_profit: profit,
  };
}

const OPTIONS: StepOption[] = [
  option("none", 0.18, 0),
  option("email_info", 0.22, 1800),
  option("call", 0.34, 8251),
  option("whatsapp", 0, 0, "not opted in to WhatsApp"),
];

function rowOf(name: string): HTMLElement {
  const label = screen.getAllByText(name)[0];
  return label.closest('[role="row"]') as HTMLElement;
}

describe("DecisionReceipt", () => {
  it("shows each step's chance and how much it changes it, never rupees", () => {
    render(<DecisionReceipt options={OPTIONS} chosen="call" slotPrice={324} price={45000} policy="model" />);
    const call = rowOf("Counsellor phone call");
    expect(within(call).getByText("34%")).toBeTruthy();
    expect(within(call).getByText("+16.0 points")).toBeTruthy();
    expect(within(call).getByLabelText("Chosen")).toBeTruthy();
    expect(screen.getByText("Chance of buying with no step:", { exact: false })).toBeTruthy();
    expect(screen.queryByText(/₹8,251|₹7,927|profit/)).toBeNull();
  });

  it("says when today's call slots went to learners a call helps more", () => {
    render(<DecisionReceipt options={OPTIONS} chosen="email_info" slotPrice={9000} policy="model" />);
    expect(
      within(rowOf("Counsellor phone call")).getByText("Today's call slots are kept for learners a call helps more."),
    ).toBeTruthy();
  });

  it("says why a step was not possible", () => {
    render(<DecisionReceipt options={OPTIONS} chosen="call" />);
    const whatsapp = rowOf("WhatsApp message");
    expect(within(whatsapp).getByText("Not possible")).toBeTruthy();
    expect(within(whatsapp).getByText("Not opted in to WhatsApp.")).toBeTruthy();
  });

  it("names the model's own pick when a step was taken by hand", () => {
    render(<DecisionReceipt options={OPTIONS} chosen="email_info" modelBest="call" policy="manual" />);
    expect(screen.getByText(/The model would have picked: counsellor phone call\./)).toBeTruthy();
    expect(within(rowOf("Send an information email")).getByLabelText("Chosen")).toBeTruthy();
  });
});
