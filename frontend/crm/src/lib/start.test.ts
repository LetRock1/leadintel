import { describe, expect, it } from "vitest";
import { doesByItself, FIRST_STEPS, glossary, JOBS } from "./start";

const rules = { control_share: 0.05, learning_steps: 0.15, daily_calls: 8, outcome_window_days: 14 };
const PAGES = ["/actions", "/callbacks", "/pipeline", "/leads", "/overview", "/campaigns", "/ab-tests", "/coupons"];
const OWNER_PAGES = ["/team", "/planner", "/learning", "/ask"];

describe("Start here", () => {
  it("gives every job a short list of first steps that lead to real pages", () => {
    for (const { value } of JOBS) {
      const steps = FIRST_STEPS[value];
      expect(steps.length).toBeGreaterThanOrEqual(3);
      expect(steps.length).toBeLessThanOrEqual(5);
      for (const s of steps) {
        expect([...PAGES, ...OWNER_PAGES]).toContain(s.to);
        expect(s.text.length).toBeLessThan(200);
      }
    }
  });

  it("explains the CRM with this CRM's own numbers", () => {
    const text = doesByItself(rules).join(" ");
    expect(text).toContain("14 days");
    expect(text).toContain("8 a day");
    expect(text).toContain("5% of learners");
    const words = glossary(rules);
    expect(words.find((w) => w.term === "Control group")?.meaning).toContain("5%");
    expect(words.find((w) => w.term === "Learning steps")?.meaning).toContain("15%");
    expect(words.find((w) => w.term === "Price of a call slot")?.meaning).toContain("8 calls a day");
  });
});
