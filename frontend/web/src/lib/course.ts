import type { Course } from "../api/types";

/** "6 Months" -> 6. */
export function months(c: Pick<Course, "duration">): number {
  const n = parseInt(c.duration, 10);
  return Number.isFinite(n) ? n : 0;
}

/** "6 Months" -> "6 months". */
export function durationText(c: Pick<Course, "duration">): string {
  return c.duration.toLowerCase();
}

export const DOMAIN_SHORT: Record<string, string> = {
  "Data Science & Analytics": "Data and AI",
  "Digital Marketing": "Marketing",
  MBA: "Management (MBA)",
  "Finance & Banking": "Finance",
  "HR Management": "HR",
  "Operations Management": "Operations",
  "Supply Chain Management": "Supply chain",
  "E-Commerce": "E-commerce",
};

export const DOMAIN_ORDER = Object.keys(DOMAIN_SHORT);

export function byDomain(courses: Course[]): { domain: string; courses: Course[] }[] {
  return DOMAIN_ORDER.map((domain) => ({ domain, courses: courses.filter((c) => c.domain === domain) })).filter(
    (g) => g.courses.length,
  );
}
