import { afterEach, describe, expect, it, vi } from "vitest";
import { reportEmailClick } from "./tracker";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reportEmailClick", () => {
  it("counts one click once, even when the page runs its effects twice", async () => {
    const bodies: string[] = [];
    const fetch = vi.fn(async (_url: string, init?: RequestInit) => {
      bodies.push(String(init?.body ?? ""));
      return new Response("{}");
    });
    vi.stubGlobal("fetch", fetch);
    await reportEmailClick("0123456789abcdef0123456789abcdef");
    await reportEmailClick("0123456789abcdef0123456789abcdef");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(JSON.parse(bodies[0])).toEqual({ token: "0123456789abcdef0123456789abcdef" });
    await reportEmailClick("fedcba9876543210fedcba9876543210"); // another email's link still counts
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
