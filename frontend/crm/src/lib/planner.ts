/**
 * The owner's planner in words: whether one more counsellor pays, and what the discount budget is doing. Kept apart
 * from the page so the verdicts can be tested.
 */
import { money } from "@xedu/shared/lib";

export interface CounsellorView {
  slots_now: number;
  extra_slots: number;
  monthly_cost: number;
  enough_data: boolean;
  note: string;
  calls_worth_making_per_day: number;
  slots_now_add_per_month: number;
  extra_adds_per_month: number;
  net_per_month: number;
}

export interface BudgetView {
  budget: number | null;
  spent: number;
  committed: number;
  left: number | null;
  price: number | null;
  used_up: boolean;
  days_left: number;
  policy: string;
  note: string;
  /** Decisions of the look-back window where a coupon added profit. */
  paying: number;
  /** How many paying decisions are needed before a month's pace is stated. */
  min_decisions?: number;
  month_without_limit: { discount: number; profit_added: number };
  extra?: { amount: number; adds_per_month: number };
}

export interface Verdict {
  tone: "good" | "neutral" | "warn";
  label: string;
  text: string;
}

export function counsellorVerdict(c: CounsellorView): Verdict {
  if (!c.enough_data) return { tone: "neutral", label: "Not enough data", text: c.note };
  if (c.extra_adds_per_month <= 0)
    return {
      tone: "neutral",
      label: "Not needed",
      text: `The team's ${c.slots_now} call slots a day are enough: about ${c.calls_worth_making_per_day.toFixed(1)} decisions a day could use a call that pays.`,
    };
  const sentence = `One more counsellor (${c.extra_slots} more calls a day) would add about ${money(c.extra_adds_per_month)} a month against ${money(c.monthly_cost)} in cost.`;
  return c.net_per_month > 0
    ? { tone: "good", label: "Worth it", text: `${sentence} That is ${money(c.net_per_month)} a month more profit.` }
    : { tone: "warn", label: "Not yet", text: `${sentence} The extra calls would not pay for the salary yet.` };
}

export function budgetVerdict(b: BudgetView): Verdict {
  if (b.budget === null)
    return {
      tone: "neutral",
      label: "No budget",
      text:
        b.paying >= (b.min_decisions ?? 30)
          ? `A coupon goes out whenever it adds more profit than its discount costs. At the current pace that is about ${money(b.month_without_limit.discount)} of discount a month, for about ${money(b.month_without_limit.profit_added)} of extra profit.`
          : `A coupon goes out whenever it adds more profit than its discount costs. The CRM has seen ${b.paying === 0 ? "no" : `only ${b.paying}`} coupon ${b.paying === 1 ? "decision" : "decisions"} that pay in the last week; it needs ${b.min_decisions ?? 30} to say what a month of coupons costs.`,
    };
  if (b.used_up)
    return {
      tone: "warn",
      label: "Used up",
      text: `${money(b.spent + b.committed)} of this month's ${money(b.budget)} is already given or promised in open coupons: the CRM sends no more coupons until next month.`,
    };
  if (!b.price)
    return {
      tone: "good",
      label: "Enough",
      text:
        b.policy === "priced"
          ? "The budget covers every coupon that pays at the current pace, so no coupon is held back."
          : `Coupons go out first come, first served until the money is used. ${b.note}`,
    };
  return {
    tone: "good",
    label: "Priced",
    text: `Money is tight, so a coupon goes out only when it adds at least ${money(b.price * 100)} of profit for every ${money(100)} of discount it uses: the budget then lasts the month and goes to the coupons that add the most.`,
  };
}
