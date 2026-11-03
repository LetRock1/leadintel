import { useQuery } from "@tanstack/react-query";
import { money } from "@xedu/shared/lib";
import { Button, Spinner } from "@xedu/shared/ui";
import { Printer } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { Course } from "../api/types";
import { useSession } from "../app/session";
import { CourseTile } from "../components/course";
import { track } from "../lib/tracker";

/** The course on one printable page: open it, then print it or save it as a PDF. */
export default function Brochure() {
  const { slug = "" } = useParams();
  const { me } = useSession();
  const course = useQuery({ queryKey: ["course", slug], queryFn: () => api.get<Course>(`/courses/${slug}`) });
  const userId = me?.user.id;
  const recorded = useRef<string | null>(null);
  useEffect(() => {
    if (!userId || !course.isSuccess || recorded.current === slug) return; // once per brochure opened
    recorded.current = slug;
    void track("brochure_dl", slug);
  }, [userId, slug, course.isSuccess]);

  if (course.isPending) return <Spinner className="m-12" label="Preparing the brochure" />;
  if (course.isError) return <p className="m-12 text-muted">This brochure could not be loaded.</p>;
  const c = course.data;
  return (
    <div className="mx-auto max-w-[820px] px-5 py-10 sm:px-8 print:max-w-none print:p-0">
      <div className="mb-6 flex items-center justify-between gap-3 print:hidden">
        <Link to={`/courses/${c.slug}`} className="text-[14px] text-muted hover:text-ink">
          Back to the course
        </Link>
        <Button variant="primary" icon={<Printer aria-hidden className="size-4" />} onClick={() => window.print()}>
          Print or save as PDF
        </Button>
      </div>
      <article className="rounded-lg border border-line bg-surface p-8 print:border-0 print:p-0">
        <header className="flex items-start gap-5 border-b border-line pb-6">
          <CourseTile course={c} size="lg" />
          <div>
            <p className="text-[13px] text-muted">X Education, {c.domain}</p>
            <h1 className="text-[30px] font-semibold leading-tight text-ink">{c.title}</h1>
            <p className="mt-1 text-[16px] text-ink-2">{c.tagline}.</p>
          </div>
        </header>
        <dl className="grid grid-cols-2 gap-4 border-b border-line py-5 sm:grid-cols-4">
          {[
            ["Duration", c.duration.toLowerCase()],
            ["Level", c.level],
            ["Fee", money(c.price)],
            ["EMI from", c.emi ? `${money(c.emi)} a month` : "Not offered"],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-[12.5px] text-muted">{k}</dt>
              <dd className="num text-[15px] font-semibold text-ink">{v}</dd>
            </div>
          ))}
        </dl>
        <section className="border-b border-line py-5">
          <h2 className="text-[18px] font-semibold text-ink">What you will be able to do</h2>
          <ul className="mt-2 list-disc pl-5 text-[14.5px] text-ink-2">
            {c.outcomes.map((o) => (
              <li key={o}>{o}</li>
            ))}
          </ul>
        </section>
        <section className="border-b border-line py-5">
          <h2 className="text-[18px] font-semibold text-ink">Curriculum</h2>
          <ol className="mt-2 grid grid-cols-1 list-decimal gap-x-8 gap-y-1 pl-5 text-[14.5px] text-ink-2 sm:grid-cols-2">
            {c.curriculum.map((m) => (
              <li key={m.module}>{m.title}</li>
            ))}
          </ol>
        </section>
        <section className="py-5">
          <h2 className="text-[18px] font-semibold text-ink">How it runs</h2>
          <p className="mt-2 text-[14.5px] text-ink-2">
            Online, with self-paced modules and a live session every week, taught by {c.instructor.name} (
            {c.instructor.role.toLowerCase()}, {c.instructor.exp} of experience). It ends with a capstone project and a
            certificate. A full refund is available within 7 days of enrolling.
          </p>
        </section>
        <footer className="border-t border-line pt-4 text-[12.5px] text-muted">
          Questions: ask the assistant on the course page, or ask for a call-back. This is a demonstration site;
          payments are simulated.
        </footer>
      </article>
    </div>
  );
}
