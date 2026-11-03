import { describe, expect, it } from "vitest";
import {
  compact,
  compactMoney,
  date,
  initials,
  money,
  parseTime,
  pct,
  plural,
  points,
  relative,
  signedMoney,
} from "./format";

describe("money", () => {
  it("writes rupees with Indian digit grouping", () => {
    expect(money(45000)).toBe("₹45,000");
    expect(money(1250000)).toBe("₹12,50,000");
    expect(money(null)).toBe("Not known");
    expect(money(Number.NaN, "")).toBe("");
  });

  it("signs a change with a real minus sign", () => {
    expect(signedMoney(4100)).toBe("+₹4,100");
    expect(signedMoney(-600)).toBe("−₹600");
    expect(signedMoney(0)).toBe("₹0");
  });

  it("compacts only from one lakh, so a thousand is never written as T", () => {
    expect(compactMoney(15200)).toBe("₹15,200");
    expect(compactMoney(2450000)).toBe("₹24.5L");
    expect(compactMoney(12000000)).toBe("₹1.2Cr");
    expect(compact(12345)).toBe("12,345");
    expect(compact(150000)).toBe("1.5L");
  });
});

describe("rates", () => {
  it("writes shares and point changes", () => {
    expect(pct(0.4123)).toBe("41%");
    expect(pct(0.4123, 1)).toBe("41.2%");
    expect(points(0.052)).toBe("+5.2 points");
    expect(points(-0.008)).toBe("−0.8 points");
    expect(points(0)).toBe("0.0 points");
  });
});

describe("times from the backend", () => {
  it("reads the backend's local time format", () => {
    const d = parseTime("2026-10-17 16:52:03");
    expect(d?.getFullYear()).toBe(2026);
    expect(d?.getHours()).toBe(16);
    expect(parseTime("not a time")).toBeNull();
    expect(date("2026-10-17")).toBe("17 Oct 2026");
  });

  it("says how long ago", () => {
    const now = new Date("2026-10-17T12:00:00");
    expect(relative("2026-10-17 11:59:40", now)).toBe("just now");
    expect(relative("2026-10-17 11:57:00", now)).toBe("3 minutes ago");
    expect(relative("2026-10-16 12:00:00", now)).toBe("yesterday");
    expect(relative(null, now, "never")).toBe("never");
  });
});

describe("words", () => {
  it("makes initials and plurals", () => {
    expect(initials("Riya Sharma")).toBe("RS");
    expect(initials("  Asha  ")).toBe("A");
    expect(initials("")).toBe("?");
    expect(plural(1, "lead")).toBe("1 lead");
    expect(plural(1200, "lead")).toBe("1,200 leads");
    expect(plural(2, "person", "people")).toBe("2 people");
  });
});
