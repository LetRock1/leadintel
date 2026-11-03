import { cn, money } from "@xedu/shared/lib";
import { Link } from "react-router";
import type { Course } from "../api/types";
import { durationText } from "../lib/course";

/** The course's short code on a tile: the website's way of telling courses apart without stock photos. */
export function CourseTile({
  course,
  size = "md",
  className,
}: {
  course: Pick<Course, "abbr" | "title">;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-md bg-brand-soft font-display font-semibold tracking-[0.01em] text-brand-ink",
        size === "sm" ? "size-9 text-[11.5px]" : size === "lg" ? "size-16 text-[20px]" : "size-11 text-[13px]",
        className,
      )}
    >
      {course.abbr}
    </span>
  );
}

/** One course in a list: tile, title, one line about it, and the facts that decide (length, level, fee). */
export function CourseRow({ course, note, className }: { course: Course; note?: string; className?: string }) {
  return (
    <Link
      to={`/courses/${course.slug}`}
      className={cn(
        "group flex items-start gap-4 rounded-md px-3 py-3 transition-colors hover:bg-sunken focus-visible:bg-sunken",
        className,
      )}
    >
      <CourseTile course={course} />
      <span className="min-w-0 flex-1">
        <span className="block font-display text-[15.5px] font-semibold leading-snug text-ink group-hover:text-brand-ink">
          {course.title}
        </span>
        <span className="mt-0.5 block text-[13.5px] text-muted">{course.tagline}</span>
        <span className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[13px] text-ink-2">
          <span>{durationText(course)}</span>
          <span>{course.level}</span>
          <span className="num">{money(course.price)}</span>
          {course.emi ? <span className="num text-muted">or {money(course.emi)} a month</span> : null}
        </span>
        {note && <span className="mt-1 block text-[12.5px] text-brand-ink">{note}</span>}
      </span>
    </Link>
  );
}

/** Duration, level, fee and EMI side by side with hairline dividers. */
export function FactStrip({ course, className }: { course: Course; className?: string }) {
  const facts = [
    { label: "Duration", value: durationText(course) },
    { label: "Level", value: course.level },
    { label: "Fee", value: money(course.price) },
    { label: "EMI from", value: course.emi ? `${money(course.emi)} a month` : "Not offered" },
  ];
  return (
    <dl
      className={cn(
        "grid grid-cols-2 gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-4",
        className,
      )}
    >
      {facts.map((f) => (
        <div key={f.label} className="bg-surface px-4 py-3">
          <dt className="text-[12.5px] text-muted">{f.label}</dt>
          <dd className="num mt-0.5 text-[15.5px] font-semibold text-ink">{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}
