/**
 * The numbers behind the Learning loop page's honesty check: what each model expected the untouched control group
 * to buy, against what it did, run by run. Kept apart from the page so they can be tested on their own.
 */

/** The control-group check stored with a learning run (learning_runs.learned_json -> control). */
export interface ControlCheck {
  rows: number;
  people: number;
  buyers: number;
  actual: number | null;
  /** The share each model expected to buy: the model in use, ours (told what the CRM did) and a naive retrain. */
  predicted: {
    champion?: number | null;
    challenger?: number | null;
    naive?: number | null;
  };
  naive_prob_better?: number | null;
}

export interface RunWithControl {
  id: number;
  as_of: string;
  learned: { control?: ControlCheck | null } | null;
}

/** An effect the lead model learned, in points of buying chance for a typical lead. */
export interface LearnedEffect {
  input: string;
  label: string;
  weight: number;
  points: number;
}

export interface FooledPoint {
  date: string;
  naive: number | null;
  ours: number | null;
  actual: number;
}

function checked(r: RunWithControl): ControlCheck | null {
  const c = r.learned?.control;
  return c && c.people > 0 && typeof c.actual === "number" ? c : null;
}

/** The latest run (runs arrive newest first) whose models were checked on people of the control group. */
export function latestChecked<R extends RunWithControl>(runs: readonly R[]): (R & { control: ControlCheck }) | null {
  for (const r of runs) {
    const c = checked(r);
    if (c) return { ...r, control: c };
  }
  return null;
}

/**
 * One point per day, oldest first (the latest run of each day): the share of the control group a naive retrain and
 * ours expected to buy, and the share that bought.
 */
export function fooledOverTime(runs: readonly RunWithControl[]): FooledPoint[] {
  const byDay = new Map<string, FooledPoint>();
  for (const r of [...runs].sort((a, b) => a.as_of.localeCompare(b.as_of) || a.id - b.id)) {
    const c = checked(r);
    if (!c || c.actual === null) continue;
    const day = r.as_of.slice(0, 10);
    byDay.set(day, {
      date: day,
      naive: typeof c.predicted.naive === "number" ? c.predicted.naive : null,
      ours: typeof c.predicted.challenger === "number" ? c.predicted.challenger : null,
      actual: c.actual,
    });
  }
  return [...byDay.values()];
}

/** How much a model over-states (above 0) or under-states buying: 0.33 expected against 0.25 bought is +0.32. */
export function overstatement(expected: number | null | undefined, actual: number | null | undefined): number | null {
  if (typeof expected !== "number" || typeof actual !== "number" || actual <= 0) return null;
  return expected / actual - 1;
}

const TIME_INPUT = /^(away|age)_/;

/** The CRM's own steps (switched off when scoring "if we do nothing") apart from the learned effects of time. */
export function splitEffects(effects: readonly LearnedEffect[] | null | undefined): {
  steps: LearnedEffect[];
  time: LearnedEffect[];
} {
  const all = effects ?? [];
  return {
    steps: all.filter((e) => !TIME_INPUT.test(e.input) && Math.abs(e.points) >= 0.1),
    time: all.filter((e) => TIME_INPUT.test(e.input)),
  };
}

/** Points with a sign and a true minus: 5.8 -> "+5.8 points", -2.4 -> "−2.4 points". */
export function signedPoints(v: number, digits = 1): string {
  const n = Math.abs(v).toFixed(digits);
  if (Number(n) === 0) return `${n} points`;
  return v > 0 ? `+${n} points` : `−${n} points`;
}
