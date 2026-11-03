import { cn, money, pct, points } from "@xedu/shared/lib";
import { Check, ChevronDown, ChevronRight, HelpCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { Policy, StepOption } from "../api/types";
import { actionLabel, POLICY_HELP, POLICY_LABEL } from "../lib/labels";

export interface DecisionReceiptProps {
  options: StepOption[];
  /** The step taken (or recommended). */
  chosen?: string | null;
  /** The model's own pick, when a different step was taken (a random step for learning, or by hand). */
  modelBest?: string | null;
  policy?: Policy | null;
  /** Price of a call slot when the decision was made (only used to say why a call was not taken). */
  slotPrice?: number | null;
  /** Course fee. */
  price?: number | null;
  title?: ReactNode;
  meta?: ReactNode;
  className?: string;
  compact?: boolean;
}

/**
 * The itemised receipt of one next-best-action decision: every step the CRM could take, the chance of buying after
 * it and how much that changes the chance against doing nothing, with the chosen step marked. The CRM also weighs
 * each step's cost, any discount and today's call slots; those stay inside the decision and are not shown here.
 */
export function DecisionReceipt({
  options,
  chosen,
  modelBest,
  policy,
  slotPrice,
  price,
  title = "Decision receipt",
  meta,
  className,
  compact,
}: DecisionReceiptProps) {
  const [showMath, setShowMath] = useState(false);
  const slot = slotPrice && slotPrice > 0 ? slotPrice : 0;
  const none = options.find((o) => o.action === "none");
  const change = (o: StepOption) => (none ? o.p_convert - none.p_convert : 0);
  const picked = options.find((o) => o.action === (chosen ?? "none"));
  const row = compact ? "py-1" : "py-1.5";
  return (
    <figure className={cn("rounded-md border border-line bg-surface", className)}>
      <figcaption
        className={cn(
          "flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line",
          compact ? "px-3 py-2" : "px-4 py-3",
        )}
      >
        <span className="text-[14px] font-semibold text-ink">{title}</span>
        <span className="ml-auto text-[12.5px] text-muted">{meta}</span>
      </figcaption>
      <div className={compact ? "px-3 py-2" : "px-4 py-3"}>
        {(none || price) && (
          <p className="mb-2 text-[13px] text-muted">
            {none && (
              <>
                Chance of buying with no step: <span className="num text-ink">{pct(none.p_convert)}</span>.{" "}
              </>
            )}
            {price ? (
              <>
                Course fee <span className="num text-ink">{money(price)}</span>.
              </>
            ) : null}
          </p>
        )}
        <div role="table" aria-label="Steps compared" className="text-[13.5px]">
          <div role="row" className="grid grid-cols-[minmax(0,1fr)_3.5rem_6.5rem] gap-x-2 pb-1 text-[12px] text-muted">
            <span role="columnheader">Step</span>
            <span role="columnheader" className="text-right" title="Chance of buying within the outcome window">
              Chance
            </span>
            <span role="columnheader" className="text-right" title="Change in the chance of buying against no step">
              Change
            </span>
          </div>
          {options.map((o) => {
            const isChosen = picked?.action === o.action;
            return (
              <div key={o.action} role="row" className={cn("-mx-2 rounded-xs px-2", isChosen && "bg-brand-soft")}>
                <div className={cn("grid grid-cols-[minmax(0,1fr)_3.5rem_6.5rem] items-baseline gap-x-2", row)}>
                  <span role="cell" className="flex min-w-0 items-baseline">
                    {isChosen ? (
                      <Check aria-label="Chosen" className="mr-1.5 size-3.5 shrink-0 self-center text-brand-ink" />
                    ) : (
                      <span aria-hidden className="mr-1.5 size-3.5 shrink-0" />
                    )}
                    <span
                      className={cn(
                        "truncate",
                        o.blocked ? "text-muted" : isChosen ? "font-medium text-ink" : "text-ink-2",
                      )}
                    >
                      {o.label || actionLabel(o.action)}
                    </span>
                    <span aria-hidden className="leader" />
                  </span>
                  <span role="cell" className="num text-right text-ink-2">
                    {o.blocked ? "" : pct(o.p_convert)}
                  </span>
                  <span
                    role="cell"
                    className={cn(
                      "num text-right",
                      o.blocked ? "text-muted" : isChosen ? "font-semibold text-ink" : "text-ink",
                    )}
                  >
                    {o.blocked ? "Not possible" : o.action === "none" ? "" : points(change(o))}
                  </span>
                </div>
                {o.blocked && <p className="-mt-0.5 pb-1 pl-5 text-[12.5px] text-muted">{capitalise(o.blocked)}</p>}
                {!o.blocked && o.action === "call" && slot > 0 && !isChosen && change(o) > 0 && (
                  <p className="-mt-0.5 pb-1 pl-5 text-[12.5px] text-muted">
                    Today&apos;s call slots are kept for learners a call helps more.
                  </p>
                )}
              </div>
            );
          })}
        </div>
        {picked && (
          <div className="mt-2 border-t-[3px] border-double border-line-strong pt-2">
            <div className="flex items-baseline gap-3 text-[14px]">
              <span className="font-semibold text-ink">{picked.label || actionLabel(picked.action)}</span>
              <span className="num ml-auto font-semibold text-ink">
                {picked.action === "none" ? pct(picked.p_convert) : points(change(picked))}
              </span>
            </div>
            <PolicyLine policy={policy} chosen={picked.action} modelBest={modelBest} />
            <div className="mt-2 border-t border-line/60 pt-2">
              <button
                type="button"
                onClick={() => setShowMath((v) => !v)}
                className="flex items-center gap-1.5 text-[12px] font-medium text-brand hover:underline"
              >
                <HelpCircle className="size-3.5" />
                {showMath ? "Hide decision calculation" : "Why was this step preferred? (Calculation & explainability)"}
                {showMath ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
              </button>
              {showMath && (
                <div className="mt-2 space-y-3 rounded border border-line bg-canvas p-3 text-[12px] text-ink-2">
                  <div>
                    <p className="font-semibold text-ink">
                      1. How ML Influences This (Causal Uplift, Not Naive Scoring)
                    </p>
                    <p className="mt-0.5 text-[11.5px] text-muted">
                      A standard CRM only predicts static buying likelihood and blindly discounts warm leads. Our ML
                      S-Learner model estimates the <em>counterfactual probability vector</em>: what this specific
                      person will do under each intervention. It detects when discounts cannibalize organic purchases
                      (producing negative ΔProfit).
                    </p>
                  </div>

                  <div>
                    <p className="font-semibold text-ink">2. Exact Optimization Calculation</p>
                    <p className="mt-0.5 font-mono text-[11px] text-brand-ink">
                      ΔProfit(a) = [P(buy | a) × Fee × (1 − Discount)] − Action Cost − [P(buy | none) × Fee]
                    </p>
                    {price && none && picked && (
                      <div className="mt-1.5 rounded bg-surface p-2 text-[11.5px] font-mono text-ink-2 border border-line/60 space-y-0.5">
                        <p>
                          • Baseline without action: {pct(none.p_convert)} × {money(price)} ={" "}
                          {money(none.p_convert * price)}
                        </p>
                        <p>
                          • {picked.label || actionLabel(picked.action)}: {pct(picked.p_convert)} × {money(price)}
                          {picked.discount > 0 ? ` × (1 − ${pct(picked.discount)})` : ""} − {money(picked.cost)} ={" "}
                          {money(picked.expected_profit)}
                        </p>
                        <p className="font-semibold text-brand">
                          • Net Incremental Profit (ΔProfit): {money(picked.incremental_profit)}
                          {picked.net_of_slot !== undefined ? ` (Net of slot price: ${money(picked.net_of_slot)})` : ""}
                        </p>
                      </div>
                    )}
                  </div>

                  <div>
                    <p className="font-semibold text-ink">3. Every Candidate Action Evaluated</p>
                    <div className="mt-1 space-y-1">
                      {options.map((o) => {
                        const netProfit = o.incremental_profit ?? 0;
                        const isBest = o.action === picked.action;
                        return (
                          <div
                            key={o.action}
                            className={cn("flex justify-between py-0.5", isBest && "font-semibold text-brand")}
                          >
                            <span>
                              {o.label || actionLabel(o.action)}
                              {o.blocked ? ` (${o.blocked})` : ""}
                            </span>
                            <span className="num">
                              {o.blocked
                                ? "Blocked by policy"
                                : `ΔProfit: ${money(netProfit)}${
                                    o.net_of_slot !== undefined ? ` (Net of slot: ${money(o.net_of_slot)})` : ""
                                  }`}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <p className="font-semibold text-ink">4. Budget & Resource Governance Checks</p>
                    <ul className="mt-0.5 list-disc pl-4 text-[11.5px] text-muted space-y-0.5">
                      <li>
                        <strong>Call Capacity:</strong> Daily quota allocated via dynamic shadow pricing (bid price) so
                        call slots are reserved for high-uplift leads.
                      </li>
                      <li>
                        <strong>Discount Budget Approval:</strong> Governed by the owner's monthly limit (under
                        Planner); the Coupon Guard blocks discounts on leads with high organic conversion.
                      </li>
                      <li>
                        <strong>Anti-Fatigue Policy:</strong> Maximum 1 active coupon per learner, 7-day cooldown
                        between coupons, and no repetitive manual outreach within 24 hours.
                      </li>
                    </ul>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </figure>
  );
}

function PolicyLine({
  policy,
  chosen,
  modelBest,
}: {
  policy?: Policy | null;
  chosen: string;
  modelBest?: string | null;
}) {
  if (!policy) return null;
  const differs = modelBest && modelBest !== chosen;
  return (
    <p className="mt-1 text-[12.5px] text-muted">
      {POLICY_LABEL[policy]}.{" "}
      {differs && (policy === "explore" || policy === "manual")
        ? `The model would have picked: ${actionLabel(modelBest).toLowerCase()}.`
        : POLICY_HELP[policy]}
    </p>
  );
}

function capitalise(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : ".") : s;
}
