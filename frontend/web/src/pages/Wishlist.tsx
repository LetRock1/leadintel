import { useMutation, useQueryClient } from "@tanstack/react-query";
import { date, errorText } from "@xedu/shared/lib";
import { Button, buttonClass, Spinner, useToast } from "@xedu/shared/ui";
import { Heart } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import { useCart, useCourses, useWishlist } from "../api/queries";
import { CourseRow } from "../components/course";
import { usePageView } from "../lib/hooks";

export default function Wishlist() {
  usePageView();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const wishlist = useWishlist();
  const cart = useCart();
  const courses = useCourses();
  const bySlug = new Map((courses.data ?? []).map((c) => [c.slug, c]));
  const remove = useMutation({
    mutationFn: (slug: string) => api.del<{ message: string }>(`/wishlist/${slug}`),
    onSuccess: (r) => {
      toast({ tone: "info", text: r.message });
      void qc.invalidateQueries({ queryKey: ["wishlist"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const toCart = useMutation({
    mutationFn: (slug: string) => api.post("/cart", { course_slug: slug }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cart"] });
      navigate("/cart");
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const items = wishlist.data ?? [];
  const inCart = new Set((cart.data ?? []).map((c) => c.course_slug));

  return (
    <div className="mx-auto max-w-[900px] px-5 pb-10 pt-12 sm:px-8">
      <h1 className="text-[34px] font-semibold leading-tight text-ink">Saved for later</h1>
      {wishlist.isPending ? (
        <Spinner className="mt-8" />
      ) : items.length === 0 ? (
        <div className="mt-8 rounded-md border border-dashed border-line-strong px-5 py-10 text-center">
          <Heart aria-hidden className="mx-auto size-6 text-muted" />
          <p className="mt-2 text-[16px] text-ink">Nothing saved yet. Save a course from its page to compare later.</p>
          <Link to="/courses" className={buttonClass("primary", "md", "mt-4")}>
            Find a course
          </Link>
        </div>
      ) : (
        <ul className="mt-8 divide-y divide-line border-y border-line">
          {items.map((w) => {
            const c = bySlug.get(w.course_slug);
            return (
              <li key={w.course_slug} className="flex flex-wrap items-center gap-3 py-2">
                <div className="min-w-0 flex-1 basis-80">
                  {c ? <CourseRow course={c} note={`Saved ${date(w.added_at)}`} className="-mx-3" /> : w.course_title}
                </div>
                <div className="flex gap-2">
                  {inCart.has(w.course_slug) ? (
                    <Link to="/cart" className={buttonClass("secondary", "sm")}>
                      In your cart
                    </Link>
                  ) : (
                    <Button
                      size="sm"
                      variant="primary"
                      loading={toCart.isPending && toCart.variables === w.course_slug}
                      onClick={() => toCart.mutate(w.course_slug)}
                    >
                      Enrol
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={remove.isPending && remove.variables === w.course_slug}
                    onClick={() => remove.mutate(w.course_slug)}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
