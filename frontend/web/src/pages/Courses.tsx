import { Input, Spinner } from "@xedu/shared/ui";
import { Search } from "lucide-react";
import { useState } from "react";
import { useCourses } from "../api/queries";
import { CourseRow } from "../components/course";
import { byDomain, DOMAIN_SHORT } from "../lib/course";
import { usePageView } from "../lib/hooks";

export default function Courses() {
  usePageView();
  const courses = useCourses();
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const shown = (courses.data ?? []).filter(
    (c) =>
      !needle ||
      [c.title, c.tagline, c.domain, ...c.outcomes, ...c.curriculum.map((m) => m.title)]
        .join(" ")
        .toLowerCase()
        .includes(needle),
  );
  const groups = byDomain(shown);

  return (
    <div className="mx-auto max-w-[1200px] px-5 pb-10 pt-12 sm:px-8">
      <h1 className="text-[34px] font-semibold leading-tight text-ink sm:text-[40px]">All courses</h1>
      <p className="mt-3 max-w-[62ch] text-[16px] text-ink-2">
        24 programmes in eight areas. Every one is online, with weekly live sessions and a capstone project.
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-4">
        <div className="relative w-full max-w-sm">
          <Search
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          />
          <Input
            type="search"
            aria-label="Search the courses"
            placeholder="Search: SQL, branding, Excel, hiring"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="h-10 pl-9"
          />
        </div>
        <nav aria-label="Areas" className="flex flex-wrap gap-x-4 gap-y-1 text-[14px]">
          {groups.map((g) => (
            <a
              key={g.domain}
              href={`#${g.domain.replace(/\W+/g, "-").toLowerCase()}`}
              className="text-ink-2 hover:text-brand-ink"
            >
              {DOMAIN_SHORT[g.domain] ?? g.domain}
            </a>
          ))}
        </nav>
      </div>
      {courses.isPending ? (
        <Spinner className="mt-10" label="Loading the courses" />
      ) : groups.length === 0 ? (
        <p className="mt-10 text-[15px] text-muted">
          No course mentions &ldquo;{q}&rdquo;. Try a broader word, or ask the help assistant.
        </p>
      ) : (
        groups.map((g) => (
          <section key={g.domain} id={g.domain.replace(/\W+/g, "-").toLowerCase()} className="mt-12 scroll-mt-24">
            <h2 className="border-b border-line pb-2 text-[22px] font-semibold text-ink">{g.domain}</h2>
            <ul className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 md:grid-cols-2 xl:grid-cols-3">
              {g.courses.map((c) => (
                <li key={c.slug}>
                  <CourseRow course={c} className="-mx-3" />
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
