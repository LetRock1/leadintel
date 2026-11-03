import { describe, expect, it } from "vitest";
import { budgetVerdict, counsellorVerdict, type BudgetView, type CounsellorView } from "./planner";

const counsellor: CounsellorView = {
  slots_now: 8,
  extra_slots: 8,
  monthly_cost: 35000,
  enough_data: true,
  note: "",
  calls_worth_making_per_day: 19.6,
  slots_now_add_per_month: 1120000,
  extra_adds_per_month: 318000,
  net_per_month: 283000,
};

const budget: BudgetView = {
  budget: null,
  spent: 0,
  committed: 0,
  left: null,
  price: 0,
  used_up: false,
  days_left: 12,
  policy: "priced",
  note: "",
  paying: 120,
  month_without_limit: { discount: 90000, profit_added: 240000 },
};

describe("the counsellor verdict", () => {
  it("says hire when the extra calls add more than the salary", () => {
    expect(counsellorVerdict(counsellor).label).toBe("Worth it");
  });
  it("says not yet when they add less, and not needed when calls are not scarce", () => {
    expect(counsellorVerdict({ ...counsellor, extra_adds_per_month: 20000, net_per_month: -15000 }).label).toBe(
      "Not yet",
    );
    expect(counsellorVerdict({ ...counsellor, extra_adds_per_month: 0, net_per_month: -35000 }).label).toBe(
      "Not needed",
    );
    expect(counsellorVerdict({ ...counsellor, enough_data: false, note: "Only 3 decisions" }).text).toBe(
      "Only 3 decisions",
    );
  });
});

describe("the discount budget verdict", () => {
  it("explains each state of the budget", () => {
    expect(budgetVerdict(budget).label).toBe("No budget");
    expect(budgetVerdict(budget).text).toContain("₹90,000");
    expect(budgetVerdict({ ...budget, paying: 0 }).text).toContain("has seen no coupon decisions that pay");
    // a handful of decisions is too few to say what a month costs
    const few = budgetVerdict({ ...budget, paying: 2, min_decisions: 30 }).text;
    expect(few).toContain("only 2 coupon decisions that pay");
    expect(few).not.toContain("₹90,000");
    const usedUp = budgetVerdict({
      ...budget,
      budget: 50000,
      spent: 42000,
      committed: 9000,
      left: -1000,
      used_up: true,
    });
    expect(usedUp.label).toBe("Used up");
    expect(usedUp.text).toContain("₹51,000 of this month's ₹50,000");
    expect(budgetVerdict({ ...budget, budget: 50000, left: 30000, price: 0 }).label).toBe("Enough");
    expect(budgetVerdict({ ...budget, budget: 50000, left: 30000, price: 0.8 }).label).toBe("Priced");
  });
});
