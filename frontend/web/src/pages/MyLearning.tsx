import { useQuery } from "@tanstack/react-query";
import { date, dateTime, money } from "@xedu/shared/lib";
import { buttonClass, Spinner } from "@xedu/shared/ui";
import { ArrowRightLeft, BookOpen } from "lucide-react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useCourses } from "../api/queries";
import type { Dashboard, Recommendation } from "../api/types";
import { useMe } from "../app/session";
import { CourseRow, CourseTile } from "../components/course";
import { usePageView } from "../lib/hooks";

export default function MyLearning() {
  usePageView();
  const me = useMe();
  const courses = useCourses();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/dashboard") });
  const recs = useQuery({
    queryKey: ["recommendations"],
    queryFn: () => api.get<{ items: Recommendation[] }>("/recommendations"),
    select: (d) => d.items,
  });
  const bySlug = new Map((courses.data ?? []).map((c) => [c.slug, c]));

  if (dash.isPending) return <Spinner className="m-12" label="Loading your learning" />;
  if (dash.isError)
    return <p className="m-12 text-muted">Your learning could not be loaded. Reload the page to try again.</p>;
  const d = dash.data;
  const first = me.user.name.split(" ")[0];

  return (
    <div className="mx-auto max-w-[1200px] px-5 pb-10 pt-12 sm:px-8">
      <h1 className="text-[34px] font-semibold leading-tight text-ink">My learning</h1>
      <p className="mt-2 text-[16px] text-ink-2">
        {d.purchases.length ? `Welcome back, ${first}.` : `Hello ${first}. When you enrol, your courses appear here.`}
      </p>

      <div className="mt-10 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          <section aria-labelledby="enrolled-title">
            <h2 id="enrolled-title" className="text-[22px] font-semibold text-ink">
              Your courses
            </h2>
            {d.purchases.length === 0 ? (
              <div className="mt-4 rounded-md border border-dashed border-line-strong px-5 py-8">
                <BookOpen aria-hidden className="size-5 text-muted" />
                <p className="mt-2 text-[15px] text-ink">You have not enrolled in a course yet.</p>
                <Link to="/courses" className={buttonClass("primary", "md", "mt-4")}>
                  Find a course
                </Link>
              </div>
            ) : (
              <ul className="mt-4 divide-y divide-line border-y border-line">
                {d.purchases.map((p) => {
                  const c = bySlug.get(p.course_slug);
                  return (
                    <li key={p.id} className="flex flex-wrap items-center gap-4 py-4">
                      {c && <CourseTile course={c} />}
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/courses/${p.course_slug}`}
                          className="font-display text-[16px] font-semibold text-ink hover:text-brand-ink"
                        >
                          {p.course_title}
                        </Link>
                        <p className="text-[13.5px] text-muted">
                          Enrolled {date(p.purchased_at)}, paid {money(p.price_paid)}
                          {p.coupon_used ? ` with ${p.coupon_used}` : ""}
                        </p>
                      </div>
                      <Link
                        to={`/courses/${p.course_slug}#reviews-title`}
                        className="text-[14px] font-medium text-brand-ink hover:underline"
                      >
                        Review it
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section aria-labelledby="recs-title" className="mt-12">
            <h2 id="recs-title" className="text-[22px] font-semibold text-ink">
              Picked for you
            </h2>
            <p className="mt-1 text-[14px] text-muted">
              From your profile, the courses you looked at, and what learners like you took.
            </p>
            {recs.isPending ? (
              <Spinner className="mt-4" />
            ) : (
              <ul className="mt-3 grid grid-cols-1 gap-x-6 md:grid-cols-2">
                {(recs.data ?? []).map((r) => {
                  const c = r.slug ? bySlug.get(r.slug) : undefined;
                  return c ? (
                    <li key={r.title}>
                      <CourseRow course={c} note={r.reason} className="-mx-3" />
                    </li>
                  ) : null;
                })}
              </ul>
            )}
          </section>
        </div>

        <aside className="flex flex-col gap-8">
          {d.next_steps.length > 0 && (
            <section aria-labelledby="steps-title">
              <h2 id="steps-title" className="text-[17px] font-semibold text-ink">
                Next steps
              </h2>
              <ul className="mt-3 flex flex-col gap-3">
                {d.next_steps.map((s) => (
                  <li key={s.label}>
                    <Link
                      to={s.to}
                      className="group block rounded-md border border-line bg-surface px-4 py-3 hover:border-brand"
                    >
                      <span className="block text-[14.5px] font-medium text-ink group-hover:text-brand-ink">
                        {s.label}
                      </span>
                      <span className="block text-[13px] text-muted">{s.why}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {d.coupons.length > 0 && (
            <section aria-labelledby="coupons-title">
              <h2 id="coupons-title" className="text-[17px] font-semibold text-ink">
                Your coupons
              </h2>
              <ul className="mt-3 flex flex-col gap-2">
                {d.coupons.map((c) => (
                  <li key={c.id} className="rounded-md border border-dashed border-brand/50 bg-brand-soft/60 px-4 py-3">
                    <p className="num text-[15px] font-semibold tracking-[0.04em] text-brand-ink">{c.coupon_code}</p>
                    <p className="text-[13px] text-ink-2">
                      {c.discount_pct}% off{c.expires_at ? `, until ${dateTime(c.expires_at)}` : ""}. Enter it at
                      checkout.
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {(d.cart.length > 0 || d.wishlist.length > 0) && (
            <section aria-labelledby="saved-title">
              <h2 id="saved-title" className="text-[17px] font-semibold text-ink">
                Saved for later
              </h2>
              <ul className="mt-3 flex flex-col gap-1.5 text-[14px]">
                {d.cart.length > 0 && (
                  <li>
                    <Link to="/cart" className="text-brand-ink hover:underline">
                      {d.cart.length} {d.cart.length === 1 ? "course" : "courses"} in your cart
                    </Link>
                  </li>
                )}
                {d.wishlist.length > 0 && (
                  <li>
                    <Link to="/wishlist" className="text-brand-ink hover:underline">
                      {d.wishlist.length} on your wishlist
                    </Link>
                  </li>
                )}
              </ul>
            </section>
          )}
          <Link to="/settings" className="inline-flex items-center gap-2 text-[14px] text-muted hover:text-ink">
            <ArrowRightLeft aria-hidden className="size-4" />
            Profile, emails and calls, your data
          </Link>
        </aside>
      </div>
    </div>
  );
}
