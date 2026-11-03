import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, cn, date, errorText, money } from "@xedu/shared/lib";
import {
  Button,
  buttonClass,
  Dialog,
  EmptyState,
  Field,
  Notice,
  Select,
  Spinner,
  Textarea,
  useToast,
} from "@xedu/shared/ui";
import { BookOpen, Check, Download, Heart, Phone, PlayCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import { useCart, useWishlist } from "../api/queries";
import type { Course, Purchase, Question, Review } from "../api/types";
import { useSession } from "../app/session";
import { CallbackDialog } from "../components/CallbackForm";
import { CourseTile, FactStrip } from "../components/course";
import { openAssistant } from "../lib/assistant-bus";
import { DOMAIN_SHORT } from "../lib/course";
import { usePageView, useSeen } from "../lib/hooks";
import { track } from "../lib/tracker";

const SLIDE_MS = 7000;

/** A 35-second overview of the programme in five slides (counts as watching the overview). */
function Overview({ course, onClose }: { course: Course; onClose: () => void }) {
  const [i, setI] = useState(0);
  const started = useRef(0);
  const slides = [
    { title: course.title, body: <p className="text-[18px] text-ink-2">{course.tagline}.</p> },
    {
      title: "What you will be able to do",
      body: (
        <ul className="flex flex-col gap-2 text-[17px] text-ink">
          {course.outcomes.map((o) => (
            <li key={o} className="flex gap-2.5">
              <Check aria-hidden className="mt-1 size-4 shrink-0 text-brand-ink" />
              {o}
            </li>
          ))}
        </ul>
      ),
    },
    {
      title: `${course.curriculum.length} modules`,
      body: (
        <ol className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-[15.5px] text-ink sm:grid-cols-2">
          {course.curriculum.map((m) => (
            <li key={m.module}>{m.title}</li>
          ))}
        </ol>
      ),
    },
    {
      title: "Who teaches it",
      body: (
        <p className="text-[17px] text-ink-2">
          {course.instructor.name}, {course.instructor.role.toLowerCase()}, with {course.instructor.exp} of experience.
          Live sessions every week, and the modules in between at your own pace.
        </p>
      ),
    },
    {
      title: `${course.duration.toLowerCase()}, ${money(course.price)}`,
      body: (
        <p className="text-[17px] text-ink-2">
          {course.emi ? `Or ${money(course.emi)} a month. ` : ""}A full refund if you change your mind within 7 days of
          enrolling.
        </p>
      ),
    },
  ];
  useEffect(() => {
    started.current = Date.now();
    return () => {
      const seconds = (Date.now() - started.current) / 1000;
      // React mounts twice while it checks the code in development: an overview "watched" for no time is not one
      if (seconds >= 0.25) void track("video_play", course.slug, seconds);
    };
  }, [course.slug]);
  useEffect(() => {
    if (i >= slides.length - 1) return;
    const t = window.setTimeout(() => setI((x) => x + 1), SLIDE_MS);
    return () => window.clearTimeout(t);
  }, [i, slides.length]);
  const s = slides[i];
  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`${course.title}: the overview`}
      description="Five slides, about 35 seconds."
    >
      <div className="flex gap-1" aria-hidden>
        {slides.map((_, k) => (
          <span key={k} className="h-1 flex-1 overflow-hidden rounded-full bg-sunken">
            <span
              className={cn(
                "block h-full bg-brand",
                k < i ? "w-full" : k === i ? "w-full origin-left animate-[grow_7s_linear]" : "w-0",
              )}
              style={k === i ? { animationDuration: `${SLIDE_MS}ms` } : undefined}
            />
          </span>
        ))}
      </div>
      <div className="flex min-h-64 flex-col justify-center py-8" aria-live="polite">
        <h3 className="text-[26px] font-semibold text-ink">{s.title}</h3>
        <div className="mt-4">{s.body}</div>
      </div>
      <div className="flex items-center justify-between">
        <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => setI(i - 1)}>
          Previous
        </Button>
        <span className="num text-[13px] text-muted">
          {i + 1} of {slides.length}
        </span>
        {i < slides.length - 1 ? (
          <Button size="sm" variant="ghost" onClick={() => setI(i + 1)}>
            Next
          </Button>
        ) : (
          <Button size="sm" variant="primary" onClick={onClose}>
            Done
          </Button>
        )}
      </div>
    </Dialog>
  );
}

function Stars({ rating }: { rating: number }) {
  return (
    <span className="inline-flex items-center gap-0.5" role="img" aria-label={`${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <svg
          key={n}
          viewBox="0 0 20 20"
          className={cn("size-4", n <= rating ? "text-brand" : "text-line-strong")}
          aria-hidden
        >
          <path fill="currentColor" d="M10 1.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L10 14.9l-5.2 2.7 1-5.8L1.5 7.7l5.9-.9z" />
        </svg>
      ))}
    </span>
  );
}

function Reviews({ slug, enrolled }: { slug: string; enrolled: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const ref = useRef<HTMLElement>(null);
  useSeen(ref, "testimonial_view", slug);
  const reviews = useQuery({
    queryKey: ["reviews", slug],
    queryFn: () => api.get<{ reviews: Review[] }>(`/reviews/${slug}`),
  });
  const [rating, setRating] = useState("5");
  const [text, setText] = useState("");
  const write = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/reviews", { course_slug: slug, rating: Number(rating), review_text: text }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      setText("");
      void qc.invalidateQueries({ queryKey: ["reviews", slug] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const list = reviews.data?.reviews ?? [];
  const avg = list.length ? list.reduce((s, r) => s + r.rating, 0) / list.length : null;
  return (
    <section ref={ref} aria-labelledby="reviews-title" className="scroll-mt-24">
      <div className="flex flex-wrap items-baseline gap-x-4">
        <h2 id="reviews-title" className="text-[24px] font-semibold text-ink">
          Reviews
        </h2>
        {avg !== null && (
          <p className="text-[14px] text-muted">
            {avg.toFixed(1)} out of 5 from {list.length} {list.length === 1 ? "learner" : "learners"} who enrolled
          </p>
        )}
      </div>
      {reviews.isPending ? (
        <Spinner className="mt-4" />
      ) : list.length === 0 ? (
        <p className="mt-3 text-[15px] text-muted">No reviews yet. Only people who enrolled can review a course.</p>
      ) : (
        <ul className="mt-4 flex flex-col divide-y divide-line border-y border-line">
          {list.slice(0, 8).map((r) => (
            <li key={r.id} className="py-4">
              <div className="flex items-center gap-3">
                <Stars rating={r.rating} />
                <span className="text-[14px] font-medium text-ink">{r.name}</span>
                <span className="text-[13px] text-muted">{date(r.created_at)}</span>
              </div>
              {r.review_text && <p className="mt-1.5 max-w-[70ch] text-[15px] text-ink-2">{r.review_text}</p>}
            </li>
          ))}
        </ul>
      )}
      {enrolled && (
        <form
          className="mt-5 max-w-xl rounded-md border border-line bg-surface p-4"
          onSubmit={(e) => {
            e.preventDefault();
            write.mutate();
          }}
        >
          <p className="text-[14px] font-medium text-ink">Review this course</p>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-[9rem_1fr]">
            <Field label="Rating">
              <Select
                value={rating}
                onChange={(e) => setRating(e.target.value)}
                options={[5, 4, 3, 2, 1].map((n) => ({ value: String(n), label: `${n} out of 5` }))}
              />
            </Field>
            <Field label="Your review" optional>
              <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
            </Field>
          </div>
          <Button type="submit" size="sm" variant="primary" className="mt-3" loading={write.isPending}>
            Publish the review
          </Button>
        </form>
      )}
    </section>
  );
}

function Questions({ slug }: { slug: string }) {
  const { me } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const location = useLocation();
  const qna = useQuery({ queryKey: ["qna", slug], queryFn: () => api.get<{ questions: Question[] }>(`/qna/${slug}`) });
  const [text, setText] = useState("");
  const ask = useMutation({
    mutationFn: () => api.post<{ message: string }>("/qna", { course_slug: slug, question: text }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      setText("");
      void qc.invalidateQueries({ queryKey: ["qna", slug] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const answered = (qna.data?.questions ?? []).filter((q) => q.answer);
  return (
    <section aria-labelledby="qna-title">
      <h2 id="qna-title" className="text-[24px] font-semibold text-ink">
        Questions and answers
      </h2>
      {answered.length === 0 ? (
        <p className="mt-3 text-[15px] text-muted">No answered questions yet. Ask the first one.</p>
      ) : (
        <ul className="mt-4 flex flex-col divide-y divide-line border-y border-line">
          {answered.slice(0, 8).map((q) => (
            <li key={q.id} className="py-4">
              <p className="text-[15px] font-medium text-ink">{q.question}</p>
              <p className="mt-1.5 max-w-[70ch] text-[15px] text-ink-2">{q.answer}</p>
              <p className="mt-1 text-[12.5px] text-muted">
                Asked by {q.user_name}. Answered by {q.answered_by ?? "the X Education team"}
                {q.answered_at ? `, ${date(q.answered_at)}` : ""}.
              </p>
            </li>
          ))}
        </ul>
      )}
      {me ? (
        <form
          className="mt-5 flex max-w-xl flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim().length >= 5) ask.mutate();
          }}
        >
          <Field label="Your question" hint="The answer is published here and emailed to you.">
            <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} />
          </Field>
          <div>
            <Button type="submit" size="sm" loading={ask.isPending} disabled={text.trim().length < 5}>
              Ask the question
            </Button>
          </div>
        </form>
      ) : (
        <p className="mt-4 text-[14px] text-ink-2">
          <Link to="/login" state={{ from: location.pathname }} className="font-medium text-brand-ink hover:underline">
            Sign in
          </Link>{" "}
          to ask a question.
        </p>
      )}
    </section>
  );
}

export default function CourseDetail() {
  const { slug = "" } = useParams();
  const { me } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const toast = useToast();
  const cart = useCart();
  const wishlist = useWishlist();
  const purchases = useQuery({
    queryKey: ["purchases"],
    queryFn: () => api.get<{ purchases: Purchase[] }>("/purchases"),
    enabled: Boolean(me),
    select: (d) => d.purchases,
  });
  const course = useQuery({ queryKey: ["course", slug], queryFn: () => api.get<Course>(`/courses/${slug}`) });
  const fees = useRef<HTMLElement>(null);
  const [overview, setOverview] = useState(false);
  const [calling, setCalling] = useState(false);
  usePageView(slug, course.isSuccess);
  useSeen(fees, "pricing_view", slug);

  const inCart = Boolean(cart.data?.some((c) => c.course_slug === slug));
  const saved = Boolean(wishlist.data?.some((w) => w.course_slug === slug));
  const enrolled = Boolean(purchases.data?.some((p) => p.course_slug === slug));

  const signInFirst = () => navigate("/login", { state: { from: location.pathname } });
  const addToCart = useMutation({
    mutationFn: () => api.post<{ message: string }>("/cart", { course_slug: slug }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cart"] });
      navigate("/cart");
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const save = useMutation({
    mutationFn: () =>
      saved
        ? api.del<{ message: string }>(`/wishlist/${slug}`)
        : api.post<{ message: string }>("/wishlist", { course_slug: slug }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["wishlist"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  if (course.isPending) return <Spinner className="m-12" label="Loading the course" />;
  if (course.isError) {
    const missing = course.error instanceof ApiError && course.error.status === 404;
    return (
      <div className="mx-auto max-w-[1200px] px-5 py-16 sm:px-8">
        <EmptyState
          icon={BookOpen}
          title={missing ? "This course does not exist" : "This course could not be loaded"}
          action={
            <Link to="/courses" className={buttonClass("primary")}>
              See all courses
            </Link>
          }
        >
          {missing ? "It may have been renamed. Every course is on the courses page." : errorText(course.error)}
        </EmptyState>
      </div>
    );
  }
  const c = course.data;

  const enrol = enrolled ? (
    <Link to="/my-learning" className={buttonClass("primary", "lg", "w-full")}>
      Go to my learning
    </Link>
  ) : inCart ? (
    <Link to="/cart" className={buttonClass("primary", "lg", "w-full")}>
      In your cart: check out
    </Link>
  ) : (
    <Button
      variant="primary"
      size="lg"
      className="w-full"
      loading={addToCart.isPending}
      onClick={() => (me ? addToCart.mutate() : signInFirst())}
    >
      Enrol now
    </Button>
  );

  return (
    <div className="mx-auto max-w-[1200px] px-5 pb-10 pt-8 sm:px-8">
      <nav aria-label="Breadcrumb" className="text-[13.5px] text-muted">
        <Link to="/courses" className="hover:text-ink">
          Courses
        </Link>
        <span aria-hidden className="mx-2">
          /
        </span>
        <Link to={`/courses#${c.domain.replace(/\W+/g, "-").toLowerCase()}`} className="hover:text-ink">
          {DOMAIN_SHORT[c.domain] ?? c.domain}
        </Link>
      </nav>

      <div className="mt-6 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          <div className="flex items-start gap-5">
            <CourseTile course={c} size="lg" />
            <div className="min-w-0">
              <h1 className="text-[32px] font-semibold leading-tight tracking-[-0.015em] text-ink sm:text-[38px]">
                {c.title}
              </h1>
              <p className="mt-2 text-[17px] text-ink-2">{c.tagline}.</p>
            </div>
          </div>
          <FactStrip course={c} className="mt-8" />
          <div className="mt-5 flex flex-wrap gap-2">
            <Button icon={<PlayCircle aria-hidden className="size-4" />} onClick={() => setOverview(true)}>
              Watch the 35-second overview
            </Button>
            <Link
              to={`/courses/${c.slug}/brochure`}
              className={buttonClass("secondary", "md")}
              onClick={(e) => {
                if (!me) {
                  e.preventDefault();
                  signInFirst();
                }
              }}
            >
              <Download aria-hidden className="size-4" />
              Brochure
            </Link>
            <Button
              variant="ghost"
              icon={<Heart aria-hidden className={cn("size-4", saved && "fill-current text-brand")} />}
              loading={save.isPending}
              onClick={() => (me ? save.mutate() : signInFirst())}
            >
              {saved ? "Saved" : "Save for later"}
            </Button>
          </div>

          <section aria-labelledby="outcomes-title" className="mt-14">
            <h2 id="outcomes-title" className="text-[24px] font-semibold text-ink">
              What you will be able to do
            </h2>
            <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {c.outcomes.map((o) => (
                <li key={o} className="flex gap-3 text-[15.5px] text-ink">
                  <Check aria-hidden className="mt-1 size-4 shrink-0 text-brand-ink" />
                  {o}
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="curriculum-title" className="mt-14">
            <h2 id="curriculum-title" className="text-[24px] font-semibold text-ink">
              Curriculum
            </h2>
            <p className="mt-1 text-[15px] text-muted">
              {c.curriculum.length} modules over {c.duration.toLowerCase()}, with a live session every week.
            </p>
            <ol className="mt-5 border-l-2 border-line">
              {c.curriculum.map((m, i) => (
                <li key={m.module} className="relative pb-5 pl-6 last:pb-0">
                  <span className="num absolute -left-[13px] top-0 flex size-6 items-center justify-center rounded-full border-2 border-line bg-canvas text-[12px] font-semibold text-ink-2">
                    {i + 1}
                  </span>
                  <p className="text-[15.5px] font-medium text-ink">{m.title}</p>
                  <p className="text-[13px] text-muted">{m.module}</p>
                </li>
              ))}
            </ol>
          </section>

          <section aria-labelledby="instructor-title" className="mt-14">
            <h2 id="instructor-title" className="text-[24px] font-semibold text-ink">
              Your instructor
            </h2>
            <div className="mt-4 flex items-center gap-4">
              <span
                aria-hidden
                className="flex size-14 items-center justify-center rounded-full bg-sunken font-display text-[18px] font-semibold text-ink-2"
              >
                {c.instructor.name
                  .replace(/^(Dr|Prof)\.?\s+/i, "")
                  .split(" ")
                  .map((p) => p[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <div>
                <p className="text-[16px] font-medium text-ink">{c.instructor.name}</p>
                <p className="text-[14px] text-muted">
                  {c.instructor.role}, {c.instructor.exp} of experience
                </p>
              </div>
            </div>
          </section>

          <section ref={fees} aria-labelledby="fees-title" className="mt-14 scroll-mt-24">
            <h2 id="fees-title" className="text-[24px] font-semibold text-ink">
              Fees
            </h2>
            <dl className="mt-4 max-w-md text-[15.5px]">
              <div className="flex items-baseline border-b border-line py-2">
                <dt className="text-ink-2">Full fee</dt>
                <dd className="num ml-auto font-semibold text-ink">{money(c.price)}</dd>
              </div>
              {c.emi && (
                <div className="flex items-baseline border-b border-line py-2">
                  <dt className="text-ink-2">Or in monthly instalments</dt>
                  <dd className="num ml-auto font-semibold text-ink">{money(c.emi)} a month</dd>
                </div>
              )}
              <div className="flex items-baseline border-b border-line py-2">
                <dt className="text-ink-2">If you change your mind</dt>
                <dd className="ml-auto text-ink">Full refund within 7 days</dd>
              </div>
            </dl>
            <p className="mt-3 text-[13px] text-muted">
              Payments on this demonstration site are simulated: nothing is charged.
            </p>
          </section>

          <div className="mt-14">
            <Reviews slug={c.slug} enrolled={enrolled} />
          </div>
          <div className="mt-14">
            <Questions slug={c.slug} />
          </div>
        </div>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="rounded-lg border border-line bg-surface p-5">
            <p className="num font-display text-[28px] font-semibold text-ink">{money(c.price)}</p>
            {c.emi && <p className="num text-[14px] text-muted">or {money(c.emi)} a month</p>}
            <div className="mt-4">{enrol}</div>
            <p className="mt-3 text-[13px] text-muted">Full refund within 7 days of enrolling.</p>
            <div className="mt-5 flex flex-col gap-2 border-t border-line pt-4">
              <Button
                variant="ghost"
                className="justify-start"
                icon={<Phone aria-hidden className="size-4" />}
                onClick={() => setCalling(true)}
              >
                Talk to a counsellor
              </Button>
              <Button
                variant="ghost"
                className="justify-start"
                onClick={() => openAssistant(`Tell me about ${c.title}`)}
              >
                Ask a question about this course
              </Button>
              {me && !enrolled && (
                <Link to={`/enquiry/${c.slug}`} className={buttonClass("ghost", "md", "justify-start")}>
                  Send an enquiry
                </Link>
              )}
            </div>
          </div>
          {enrolled && (
            <Notice tone="good" className="mt-4">
              You are enrolled in this course.
            </Notice>
          )}
        </aside>
      </div>
      {overview && <Overview course={c} onClose={() => setOverview(false)} />}
      {calling && <CallbackDialog courseSlug={c.slug} courseTitle={c.title} onClose={() => setCalling(false)} />}
    </div>
  );
}
