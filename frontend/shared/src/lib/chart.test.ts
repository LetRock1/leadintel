/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";
import tokens from "../styles/tokens.css?raw";
import { CHART_COLORS } from "./chart";

/** The value of a custom property inside one block of tokens.css (":root" or ".dark"). */
function token(block: string, name: string): string | undefined {
  const start = tokens.indexOf(`${block} {`);
  const body = tokens.slice(start, tokens.indexOf("}", start));
  return body.match(new RegExp(`--xe-${name}:\\s*([^;]+);`))?.[1].trim();
}

describe("chart colours", () => {
  const cases = [
    ["light", ":root"],
    ["dark", ".dark"],
  ] as const;

  it.each(cases)("repeat the %s design tokens exactly", (theme, block) => {
    const c = CHART_COLORS[theme];
    c.series.forEach((hex, i) => expect(token(block, `series-${i + 1}`)).toBe(hex));
    expect(token(block, "series-muted")).toBe(c.seriesMuted);
    expect(token(block, "grid")).toBe(c.grid);
    expect(token(block, "axis")).toBe(c.axis);
    expect(token(block, "muted")).toBe(c.text);
    expect(token(block, "ink")).toBe(c.ink);
    expect(token(block, "surface")).toBe(c.surface);
    expect(token(block, "brand")).toBe(c.brand);
  });

  it("keeps four distinct series hues per theme", () => {
    for (const theme of ["light", "dark"] as const) {
      expect(new Set(CHART_COLORS[theme].series).size).toBe(4);
    }
  });
});
