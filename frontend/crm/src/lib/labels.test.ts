/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import settingsText from "../../../../crm_settings.json?raw";
import { ACTION_LABEL, ACTION_ORDER, ACTION_SHORT, TIERS, actionLabel, tierLevel } from "./labels";

const settings = JSON.parse(settingsText) as {
  actions: Record<string, { label: string }>;
  tiers: { name: string; min_score: number }[];
};

describe("labels match crm_settings.json", () => {
  it("names every step the backend can take, in both lengths", () => {
    const keys = Object.keys(settings.actions).sort();
    expect([...ACTION_ORDER].sort()).toEqual(keys);
    for (const key of keys) {
      expect(ACTION_LABEL[key as keyof typeof ACTION_LABEL]).toBe(settings.actions[key].label);
      expect(ACTION_SHORT[key as keyof typeof ACTION_SHORT]).toBeTruthy();
    }
  });

  it("lists the tiers hottest first", () => {
    expect([...TIERS]).toEqual(settings.tiers.map((t) => t.name));
    expect(tierLevel("Target Immediately")).toBe(4);
    expect(tierLevel("Low Priority")).toBe(1);
    expect(tierLevel("Something else")).toBe(0);
  });

  it("falls back to the key for an unknown step", () => {
    expect(actionLabel("call")).toBe("Counsellor phone call");
    expect(actionLabel("call", true)).toBe("Phone call");
    expect(actionLabel(null)).toBe("No step");
    expect(actionLabel("fax")).toBe("fax");
  });
});
