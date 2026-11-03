import { useMutation, useQueryClient } from "@tanstack/react-query";
import { errorText, money } from "@xedu/shared/lib";
import { Button, buttonClass, Spinner, useToast } from "@xedu/shared/ui";
import { ShoppingBag } from "lucide-react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useCart, useCourses } from "../api/queries";
import { CourseTile } from "../components/course";
import { usePageView } from "../lib/hooks";

export default function Cart() {
  usePageView();
  const qc = useQueryClient();
  const toast = useToast();
  const cart = useCart();
  const courses = useCourses();
  const bySlug = new Map((courses.data ?? []).map((c) => [c.slug, c]));
  const remove = useMutation({
    mutationFn: (slug: string) => api.del<{ message: string }>(`/cart/${slug}`),
    onSuccess: (r) => {
      toast({ tone: "info", text: r.message });
      void qc.invalidateQueries({ queryKey: ["cart"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const items = cart.data ?? [];
  const total = items.reduce((s, i) => s + (bySlug.get(i.course_slug)?.price ?? i.price), 0);

  return (
    <div className="mx-auto max-w-[900px] px-5 pb-10 pt-12 sm:px-8">
      <h1 className="text-[34px] font-semibold leading-tight text-ink">Your cart</h1>
      {cart.isPending ? (
        <Spinner className="mt-8" />
      ) : items.length === 0 ? (
        <div className="mt-8 rounded-md border border-dashed border-line-strong px-5 py-10 text-center">
          <ShoppingBag aria-hidden className="mx-auto size-6 text-muted" />
          <p className="mt-2 text-[16px] text-ink">Your cart is empty.</p>
          <Link to="/courses" className={buttonClass("primary", "md", "mt-4")}>
            Find a course
          </Link>
        </div>
      ) : (
        <>
          <ul className="mt-8 divide-y divide-line border-y border-line">
            {items.map((i) => {
              const c = bySlug.get(i.course_slug);
              return (
                <li key={i.course_slug} className="flex items-center gap-4 py-4">
                  {c && <CourseTile course={c} />}
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/courses/${i.course_slug}`}
                      className="font-display text-[16px] font-semibold text-ink hover:text-brand-ink"
                    >
                      {i.course_title}
                    </Link>
                    {c && (
                      <p className="text-[13.5px] text-muted">
                        {c.duration.toLowerCase()}, {c.level}
                      </p>
                    )}
                  </div>
                  <p className="num text-[16px] font-semibold text-ink">{money(c?.price ?? i.price)}</p>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={remove.isPending && remove.variables === i.course_slug}
                    onClick={() => remove.mutate(i.course_slug)}
                  >
                    Remove
                  </Button>
                </li>
              );
            })}
          </ul>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
            <Link to="/courses" className="text-[14px] font-medium text-brand-ink hover:underline">
              Keep browsing
            </Link>
            <div className="flex items-center gap-5">
              <p className="text-[15px] text-ink-2">
                Total <span className="num ml-2 text-[20px] font-semibold text-ink">{money(total)}</span>
              </p>
              <Link to="/checkout" className={buttonClass("primary", "lg")}>
                Check out
              </Link>
            </div>
          </div>
          <p className="mt-3 text-right text-[13px] text-muted">A coupon can be added at checkout.</p>
        </>
      )}
    </div>
  );
}
