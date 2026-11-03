import { describe, expect, it } from "vitest";
import { byMoney, moneyLine } from "./money";

describe("the money line of a pipeline card", () => {
  it("names the step and what it adds when a step pays", () => {
    expect(moneyLine({ segment: "work", add: 8251, best: "call", p_anyway: 0.18, p_with_step: 0.34 })).toEqual({
      action: "call",
      add: 8251,
      pWithout: 0.18,
      pWith: 0.34,
      text: "with a phone call",
    });
  });

  it("offers no step when none pays, the lead is in the control group or cannot be contacted", () => {
    for (const segment of ["anyway", "wait", "control", "unreachable"] as const) {
      const line = moneyLine({ segment, add: 0, best: "none" });
      expect(line.action).toBeNull();
      expect(line.add).toBe(0);
      expect(line.text.length).toBeGreaterThan(0);
    }
    // a "work" card without a positive amount is not offered either
    expect(moneyLine({ segment: "work", add: 0, best: "call" }).action).toBeNull();
  });
});

describe("working the board by money", () => {
  it("puts the most money to add first, then the score", () => {
    const cards = [
      { user_id: 1, add: 0, score: 90 },
      { user_id: 2, add: 500, score: 10 },
      { user_id: 3, add: 500, score: 40 },
      { user_id: 4, add: 1200, score: 5 },
    ];
    expect(byMoney(cards).map((c) => c.user_id)).toEqual([4, 3, 2, 1]);
  });
});
