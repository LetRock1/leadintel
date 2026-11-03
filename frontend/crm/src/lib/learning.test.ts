import { describe, expect, it } from "vitest";
import {
  fooledOverTime,
  latestChecked,
  overstatement,
  signedPoints,
  splitEffects,
  type RunWithControl,
} from "./learning";

function run(
  id: number,
  asOf: string,
  actual: number | null,
  naive?: number,
  ours?: number,
  people = 40,
): RunWithControl {
  return {
    id,
    as_of: asOf,
    learned: {
      control: { rows: 100, people, buyers: 5, actual, predicted: { champion: 0.2, challenger: ours, naive } },
    },
  };
}

describe("the learning loop's honesty check", () => {
  it("takes the newest run that was checked on the control group", () => {
    const runs = [run(3, "2026-10-19 18:00:00", 0.1, 0.3, 0.2, 0), run(2, "2026-09-19 00:00:00", 0.14, 0.32, 0.25)];
    expect(latestChecked(runs)?.id).toBe(2);
    expect(latestChecked([run(1, "2026-05-22 00:00:00", null)])).toBeNull();
  });

  it("keeps one point a day, the latest run of that day, oldest first", () => {
    const runs = [
      run(4, "2026-10-19 18:00:00", 0.15, 0.33, 0.26),
      run(3, "2026-10-19 09:00:00", 0.1, 0.3, 0.2),
      run(2, "2026-09-19 00:00:00", 0.14, 0.32, 0.25),
    ];
    expect(fooledOverTime(runs)).toEqual([
      { date: "2026-09-19", naive: 0.32, ours: 0.25, actual: 0.14 },
      { date: "2026-10-19", naive: 0.33, ours: 0.26, actual: 0.15 },
    ]);
  });

  it("measures over-statement against what the control group bought", () => {
    expect(overstatement(0.33, 0.25)).toBeCloseTo(0.32);
    expect(overstatement(0.2, 0.25)).toBeCloseTo(-0.2);
    expect(overstatement(0.2, 0)).toBeNull();
    expect(overstatement(null, 0.25)).toBeNull();
  });

  it("separates the CRM's own steps from the learned effects of time", () => {
    const { steps, time } = splitEffects([
      { input: "call", label: "Counsellor phone call", weight: 0.74, points: 17.3 },
      { input: "email_info", label: "Send an information email", weight: 0, points: 0.04 },
      { input: "away_14_30_days", label: "Last seen 14-30 days ago", weight: -1.48, points: -21.1 },
      { input: "age_7_14_days", label: "Signed up 7-14 days ago", weight: -1.29, points: -19.4 },
    ]);
    expect(steps.map((e) => e.input)).toEqual(["call"]);
    expect(time.map((e) => e.input)).toEqual(["away_14_30_days", "age_7_14_days"]);
    expect(splitEffects(null)).toEqual({ steps: [], time: [] });
  });

  it("writes points with a sign and a true minus", () => {
    expect(signedPoints(5.8)).toBe("+5.8 points");
    expect(signedPoints(-21.14)).toBe("−21.1 points");
    expect(signedPoints(-0.04)).toBe("0.0 points");
  });
});
