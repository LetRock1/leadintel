import { describe, expect, it } from "vitest";
import { EMAIL_RE, passwordProblem } from "./password";

describe("learner passwords", () => {
  it("follow the backend's rule: 8 to 128 characters, no forced mix", () => {
    expect(passwordProblem("short")).toBe("Use at least 8 characters.");
    expect(passwordProblem("eightchr")).toBeNull();
    expect(passwordProblem("x".repeat(129))).toBe("Use at most 128 characters.");
  });

  it("accepts ordinary email addresses only", () => {
    expect(EMAIL_RE.test("riya.sharma@example.com")).toBe(true);
    expect(EMAIL_RE.test("riya@example")).toBe(false);
    expect(EMAIL_RE.test("riya sharma@example.com")).toBe(false);
  });
});
