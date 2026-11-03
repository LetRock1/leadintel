/**
 * The step line of a pipeline card: the best step now and how much it raises the chance of buying, or why nothing.
 * Kept apart from the page so it can be tested on its own.
 */
import type { ActionKey, MoneySegment, PipelineCard } from "../api/types";

export const SEGMENT_LABEL: Record<MoneySegment, string> = {
  work: "Work this",
  anyway: "Buys anyway",
  wait: "No step helps enough now",
  control: "Control group",
  unreachable: "Can't be contacted",
  lost: "Lost",
  customer: "Customer",
};

/** The step in a few words, after "with": "a phone call", "a 20% coupon email". */
export const STEP_WITH: Record<ActionKey, string> = {
  none: "no step",
  email_info: "an information email",
  email_coupon_10: "a 10% coupon email",
  email_coupon_20: "a 20% coupon email",
  call: "a phone call",
  whatsapp: "a WhatsApp message",
};

export interface MoneyLine {
  /** The step to take now, or null when there is nothing to do. */
  action: ActionKey | null;
  /** Extra profit of that step (rupees), 0 when there is no step: the order of work, never shown on a card. */
  add: number;
  /** Chance of buying with no step and with the step (0 to 1), when there is a step. */
  pWithout: number | null;
  pWith: number | null;
  text: string;
}

type CardMoney = Pick<PipelineCard, "segment" | "add" | "best"> &
  Partial<Pick<PipelineCard, "p_anyway" | "p_with_step">>;

export function moneyLine(card: CardMoney): MoneyLine {
  if (card.segment === "work" && card.best && card.best !== "none" && card.add > 0) {
    return {
      action: card.best,
      add: card.add,
      pWithout: card.p_anyway ?? null,
      pWith: card.p_with_step ?? null,
      text: `with ${STEP_WITH[card.best]}`,
    };
  }
  const text =
    card.segment === "anyway"
      ? "Likely to buy without help: no step needed"
      : card.segment === "control"
        ? "Never contacted: shows what happens without the CRM"
        : card.segment === "unreachable"
          ? "No allowed channel to contact them"
          : card.segment === "wait"
            ? "No step raises the chance enough now"
            : "";
  return { action: null, add: 0, pWithout: card.p_anyway ?? null, pWith: null, text };
}

/** Cards in the order the team should work them: where a step makes the most difference first, then the score. */
export function byMoney<T extends Pick<PipelineCard, "add" | "score" | "user_id">>(cards: readonly T[]): T[] {
  return [...cards].sort((a, b) => b.add - a.add || b.score - a.score || a.user_id - b.user_id);
}
