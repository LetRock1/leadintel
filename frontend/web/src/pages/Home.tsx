import { useMutation, useQuery } from "@tanstack/react-query";
import { cn } from "@xedu/shared/lib";
import { Button, buttonClass, Spinner, useToast } from "@xedu/shared/ui";
import { ChevronDown } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { api } from "../api/client";
import { useCourses } from "../api/queries";
import type { Course } from "../api/types";
import { useSession } from "../app/session";
import { CallbackDialog } from "../components/CallbackForm";
import { CourseRow } from "../components/course";
import { openAssistant } from "../lib/assistant-bus";
import { DOMAIN_ORDER, DOMAIN_SHORT, months } from "../lib/course";
import { usePageView } from "../lib/hooks";
import { track } from "../lib/tracker";

type Who = "student" | "working" | "seeking" | "business";
type Time = "short" | "medium" | "long";

const WHO: { value: Who; label: string }[] = [
  { value: "student", label: "a student" },
  { value: "working", label: "working" },
  { value: "seeking", label: "looking for work" },
  { value: "business", label: "running a business" },
];

const TIME: { value: Time; label: string; max: number; min: number }[] = [
  { value: "short", label: "up to 3 months", min: 0, max: 3 },
  { value: "medium", label: "4 to 6 months", min: 4, max: 6 },
  { value: "long", label: "longer than 6 months", min: 7, max: 99 },
];

/** How well a course fits the answers: the area and the time first, then the level that suits the person. */
function fit(c: Course, who: Who | null, areas: string[], time: Time | null): { score: number; why: string[] } {
  const why: string[] = [];
  let score = 0;
  if (areas.length) {
    if (!areas.includes(c.domain)) return { score: -1, why };
    score += 3;
  }
  if (time) {
    const t = TIME.find((x) => x.value === time)!;
    const m = months(c);
    if (m < t.min || m > t.max) return { score: -1, why };
    score += 2;
    why.push(c.duration.toLowerCase());
  }
  const level = c.level.toLowerCase();
  if (who === "student" || who === "seeking") {
    if (level.startsWith("advanced")) return { score: -1, why };
    if (level.startsWith("beginner")) {
      score += 2;
      why.push("no experience needed");
    }
  } else if (who === "working") {
    if (!level.startsWith("beginner")) score += 1;
    if (c.slug === "executive-mba") score += 2;
  } else if (who === "business") {
    if (["MBA", "E-Commerce", "Digital Marketing", "Finance & Banking"].includes(c.domain)) score += 2;
    if (c.slug === "mba-entrepreneurship" || c.slug === "d2c-brand-building") score += 2;
  }
  return { score, why };
}

function Chip({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "rounded-full border px-3.5 py-1.5 text-[14px] transition-colors",
        selected
          ? "border-brand bg-brand text-on-brand"
          : "border-line-strong bg-surface text-ink-2 hover:border-brand hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

/** The 24 courses as a table: one column per area, the finder's matches stand out. */
function CourseTable({ courses, match }: { courses: Course[]; match: Set<string> | null }) {
  return (
    <div className="-mx-5 overflow-x-auto px-5 pb-1 sm:mx-0 sm:px-0">
      <div className="grid min-w-[880px] grid-cols-8 gap-2.5">
        {DOMAIN_ORDER.map((d) => (
          <div key={d} className="flex flex-col gap-2.5">
            <p className="border-b border-line-strong pb-1.5 text-[12.5px] font-medium text-ink-2">{DOMAIN_SHORT[d]}</p>
            {courses
              .filter((c) => c.domain === d)
              .map((c) => {
                const on = !match || match.has(c.slug);
                return (
                  <Link
                    key={c.slug}
                    to={`/courses/${c.slug}`}
                    aria-label={`${c.title}, ${c.duration.toLowerCase()}`}
                    className={cn(
                      "group flex min-h-[124px] flex-col justify-between gap-3 rounded-md border p-3 transition-[opacity,border-color,background-color]",
                      on
                        ? "border-brand/25 bg-brand-soft hover:border-brand"
                        : "border-line bg-surface opacity-45 hover:opacity-100",
                    )}
                  >
                    <span
                      className={cn(
                        "font-display text-[22px] font-semibold leading-none",
                        on ? "text-brand-ink" : "text-ink-2",
                      )}
                    >
                      {c.abbr}
                    </span>
                    <span>
                      <span className="line-clamp-2 text-[12.5px] font-medium leading-snug text-ink">{c.title}</span>
                      <span className="num mt-1 block text-[12px] text-muted">{c.duration.toLowerCase()}</span>
                    </span>
                  </Link>
                );
              })}
          </div>
        ))}
      </div>
    </div>
  );
}

function nextSaturday(): Date {
  const d = new Date();
  const add = (6 - d.getDay() + 7) % 7 || (d.getHours() >= 12 ? 7 : 0);
  d.setDate(d.getDate() + add);
  d.setHours(11, 0, 0, 0);
  return d;
}

function LiveSession() {
  const { me } = useSession();
  const toast = useToast();
  const [when] = useState(nextSaturday);
  const reserve = useMutation({
    mutationFn: () => track("webinar_register"),
    onSuccess: () =>
      toast({
        tone: "good",
        text: `Seat reserved for ${when.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}, 11:00.`,
      }),
  });
  return (
    <section id="live-session" aria-labelledby="live-title" className="scroll-mt-24 border-y border-line bg-surface">
      <div className="mx-auto grid grid-cols-1 max-w-[1200px] items-center gap-8 px-5 py-14 sm:px-8 md:grid-cols-[auto_1fr_auto]">
        <div className="flex size-24 flex-col items-center justify-center rounded-lg border border-line-strong bg-canvas text-center">
          <span className="text-[12.5px] font-medium text-brand-ink">
            {when.toLocaleDateString("en-IN", { weekday: "short" })}
          </span>
          <span className="font-display text-[34px] font-semibold leading-none text-ink">{when.getDate()}</span>
          <span className="text-[12.5px] text-muted">{when.toLocaleDateString("en-IN", { month: "short" })}</span>
        </div>
        <div>
          <h2 id="live-title" className="text-[26px] font-semibold text-ink">
            Free live session, every Saturday at 11:00
          </h2>
          <p className="mt-2 max-w-[60ch] text-[15px] text-ink-2">
            An instructor walks through one programme: what you build, how the weeks are planned, and what it takes
            alongside a job. Bring your questions.
          </p>
        </div>
        {me ? (
          <Button
            variant="primary"
            size="lg"
            loading={reserve.isPending}
            disabled={reserve.isSuccess}
            onClick={() => reserve.mutate()}
          >
            {reserve.isSuccess ? "Seat reserved" : "Reserve a seat"}
          </Button>
        ) : (
          <Link to="/signup" className={buttonClass("primary", "lg")}>
            Create an account to join
          </Link>
        )}
      </div>
    </section>
  );
}

function Faq() {
  const faq = useQuery({
    queryKey: ["faq"],
    queryFn: () => api.get<{ faq: { key: string; question: string; answer: string }[] }>("/faq"),
    staleTime: Infinity,
  });
  const [open, setOpen] = useState<string | null>("schedule");
  if (!faq.data) return null;
  return (
    <ul className="divide-y divide-line border-y border-line">
      {faq.data.faq.map((f) => {
        const isOpen = open === f.key;
        return (
          <li key={f.key}>
            <h3 className="font-sans">
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? null : f.key)}
                className="flex w-full items-center justify-between gap-4 py-4 text-left text-[16px] font-medium text-ink"
              >
                {f.question}
                <ChevronDown
                  aria-hidden
                  className={cn("size-4 shrink-0 text-muted transition-transform", isOpen && "rotate-180")}
                />
              </button>
            </h3>
            {isOpen && <p className="max-w-[70ch] pb-5 text-[15px] text-ink-2">{f.answer}</p>}
          </li>
        );
      })}
    </ul>
  );
}

export default function Home() {
  usePageView();
  const location = useLocation();
  const courses = useCourses();
  const [who, setWho] = useState<Who | null>(null);
  const [areas, setAreas] = useState<string[]>([]);
  const [time, setTime] = useState<Time | null>(null);
  const [calling, setCalling] = useState(false);
  const active = who !== null || areas.length > 0 || time !== null;

  const ranked = useMemo(() => {
    const all = courses.data ?? [];
    return all
      .map((c) => ({ c, ...fit(c, who, areas, time) }))
      .filter((x) => x.score >= 0)
      .sort((a, b) => b.score - a.score || a.c.price - b.c.price);
  }, [courses.data, who, areas, time]);
  const match = active ? new Set(ranked.map((r) => r.c.slug)) : null;

  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }, [location.hash, courses.data]);

  const toggleArea = (d: string) => setAreas((a) => (a.includes(d) ? a.filter((x) => x !== d) : [...a, d]));

  return (
    <>
      <section className="mx-auto max-w-[1200px] px-5 pb-16 pt-12 sm:px-8 sm:pt-16">
        <h1 className="max-w-[18ch] text-[36px] font-semibold leading-[1.08] tracking-[-0.02em] text-ink sm:text-[48px]">
          Find the course that fits where you are now.
        </h1>
        <p className="mt-4 max-w-[62ch] text-[16.5px] text-ink-2">
          24 online programmes in data, marketing, management, finance, HR, operations and e-commerce. Live sessions
          every week, a project you can show, and a counsellor when you want one.
        </p>

        <div className="mt-10" aria-label="Course finder">
          <div className="flex flex-col gap-3.5">
            <div
              role="group"
              aria-labelledby="finder-who"
              className="grid grid-cols-1 items-baseline gap-2.5 sm:grid-cols-[9.5rem_1fr]"
            >
              <span id="finder-who" className="text-[14.5px] font-medium text-ink">
                I am
              </span>
              <div className="flex flex-wrap gap-2">
                {WHO.map((w) => (
                  <Chip
                    key={w.value}
                    selected={who === w.value}
                    onClick={() => setWho(who === w.value ? null : w.value)}
                  >
                    {w.label}
                  </Chip>
                ))}
              </div>
            </div>
            <div
              role="group"
              aria-labelledby="finder-area"
              className="grid grid-cols-1 items-baseline gap-2.5 sm:grid-cols-[9.5rem_1fr]"
            >
              <span id="finder-area" className="text-[14.5px] font-medium text-ink">
                I want to grow in
              </span>
              <div className="flex flex-wrap gap-2">
                {DOMAIN_ORDER.map((d) => (
                  <Chip key={d} selected={areas.includes(d)} onClick={() => toggleArea(d)}>
                    {DOMAIN_SHORT[d]}
                  </Chip>
                ))}
              </div>
            </div>
            <div
              role="group"
              aria-labelledby="finder-time"
              className="grid grid-cols-1 items-baseline gap-2.5 sm:grid-cols-[9.5rem_1fr]"
            >
              <span id="finder-time" className="text-[14.5px] font-medium text-ink">
                I can give it
              </span>
              <div className="flex flex-wrap gap-2">
                {TIME.map((t) => (
                  <Chip
                    key={t.value}
                    selected={time === t.value}
                    onClick={() => setTime(time === t.value ? null : t.value)}
                  >
                    {t.label}
                  </Chip>
                ))}
              </div>
            </div>
            <p className="text-[14px] text-muted sm:pl-[10.1rem]" aria-live="polite">
              {!active
                ? "Choose what applies; the matching courses light up."
                : ranked.length === 0
                  ? "Nothing fits all three. Try a longer time or another area."
                  : `${ranked.length} ${ranked.length === 1 ? "course fits" : "courses fit"}.`}
              {active && (
                <button
                  type="button"
                  className="ml-2 font-medium text-brand-ink hover:underline"
                  onClick={() => {
                    setWho(null);
                    setAreas([]);
                    setTime(null);
                  }}
                >
                  Start again
                </button>
              )}
            </p>
          </div>
          <div className="mt-8">
            {courses.data ? (
              <CourseTable courses={courses.data} match={match} />
            ) : (
              <Spinner label="Loading the courses" />
            )}
          </div>
        </div>

        {active && ranked.length > 0 && (
          <div className="mt-12">
            <h2 className="text-[22px] font-semibold text-ink">Courses that fit</h2>
            <ul className="mt-4 grid grid-cols-1 gap-x-6 gap-y-1 md:grid-cols-2">
              {ranked.slice(0, 6).map((r) => (
                <li key={r.c.slug}>
                  <CourseRow course={r.c} />
                </li>
              ))}
            </ul>
            {ranked.length > 6 && (
              <Link to="/courses" className="mt-3 inline-block text-[14px] font-medium text-brand-ink hover:underline">
                See all {ranked.length} that fit, and every other course
              </Link>
            )}
          </div>
        )}
      </section>

      <LiveSession />

      <section className="mx-auto grid grid-cols-1 max-w-[1200px] gap-12 px-5 py-16 sm:px-8 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <div>
          <h2 className="text-[26px] font-semibold text-ink">Questions people ask first</h2>
          <p className="mt-2 text-[15px] text-ink-2">
            Answered plainly. For anything else, ask the assistant or a counsellor.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button onClick={() => openAssistant()}>Ask a question</Button>
            <Button variant="ghost" onClick={() => setCalling(true)}>
              Talk to a counsellor
            </Button>
          </div>
        </div>
        <Faq />
      </section>
      {calling && <CallbackDialog onClose={() => setCalling(false)} />}
    </>
  );
}
