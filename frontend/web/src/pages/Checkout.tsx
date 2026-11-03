import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorText, money } from "@xedu/shared/lib";
import { Button, buttonClass, Field, Input, Notice, Spinner } from "@xedu/shared/ui";
import { Lock } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import { useCart, useCourses } from "../api/queries";
import type { CheckoutResult, Coupon, CouponCheck } from "../api/types";
import { usePageView } from "../lib/hooks";
import { track } from "../lib/tracker";

export default function Checkout() {
  usePageView();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const cart = useCart();
  const courses = useCourses();
  const coupons = useQuery({
    queryKey: ["coupons"],
    queryFn: () => api.get<{ coupons: Coupon[] }>("/coupons"),
    select: (d) => d.coupons.filter((c) => !c.used),
  });
  const [code, setCode] = useState("");
  const [applied, setApplied] = useState<CouponCheck | null>(null);
  const started = useRef(false);
  const items = cart.data ?? [];

  // opening the checkout is recorded once: the CRM follows up if the learner leaves without paying
  useEffect(() => {
    if (started.current || !items.length) return;
    started.current = true;
    void api.post("/checkout/start");
    void track("checkout_start");
  }, [items.length]);

  const check = useMutation({
    mutationFn: (c: string) => api.post<CouponCheck>("/coupons/check", { code: c }),
    onSuccess: setApplied,
  });
  const pay = useMutation({
    mutationFn: () => api.post<CheckoutResult>("/checkout", { coupon_code: applied?.code ?? "" }),
    onSuccess: (r) => {
      void qc.invalidateQueries();
      navigate("/thank-you", { replace: true, state: r });
    },
  });

  if (cart.isPending) return <Spinner className="m-12" />;
  if (!items.length) {
    return (
      <div className="mx-auto max-w-[640px] px-5 py-16 sm:px-8">
        <h1 className="text-[30px] font-semibold text-ink">Nothing to pay for</h1>
        <p className="mt-2 text-[15px] text-ink-2">Your cart is empty.</p>
        <Link to="/courses" className={buttonClass("primary", "md", "mt-5")}>
          Find a course
        </Link>
      </div>
    );
  }
  const price = (slug: string, fallback: number) => courses.data?.find((c) => c.slug === slug)?.price ?? fallback;
  const subtotal = items.reduce((s, i) => s + price(i.course_slug, i.price), 0);
  const discount = applied?.discount ?? 0;
  const total = subtotal - discount;

  return (
    <div className="mx-auto max-w-[900px] px-5 pb-10 pt-12 sm:px-8">
      <h1 className="text-[34px] font-semibold leading-tight text-ink">Checkout</h1>
      <div className="mt-8 grid grid-cols-1 gap-10 md:grid-cols-[minmax(0,1fr)_20rem]">
        <section aria-labelledby="order-title">
          <h2 id="order-title" className="text-[18px] font-semibold text-ink">
            Your order
          </h2>
          <dl className="mt-3 text-[15px]">
            {items.map((i) => (
              <div key={i.course_slug} className="flex items-baseline gap-4 border-b border-line py-2.5">
                <dt className="text-ink">{i.course_title}</dt>
                <dd className="num ml-auto text-ink">{money(price(i.course_slug, i.price))}</dd>
              </div>
            ))}
            {applied && (
              <div className="flex items-baseline gap-4 border-b border-line py-2.5">
                <dt className="text-ink-2">
                  Coupon {applied.code} ({applied.discount_pct}% off)
                </dt>
                <dd className="num ml-auto text-ink">−{money(discount)}</dd>
              </div>
            )}
            <div className="flex items-baseline gap-4 border-t-[3px] border-double border-line-strong pt-3">
              <dt className="font-semibold text-ink">To pay</dt>
              <dd className="num ml-auto text-[20px] font-semibold text-ink">{money(total)}</dd>
            </div>
          </dl>

          <form
            className="mt-8 max-w-sm"
            onSubmit={(e) => {
              e.preventDefault();
              if (code.trim()) check.mutate(code.trim());
            }}
          >
            <Field
              label="Coupon code"
              error={check.isError ? errorText(check.error) : null}
              trailing={
                <Button type="submit" loading={check.isPending} disabled={!code.trim()}>
                  Apply
                </Button>
              }
            >
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                className="num uppercase"
                maxLength={40}
              />
            </Field>
            {coupons.data && coupons.data.length > 0 && !applied && (
              <p className="mt-2 text-[13px] text-muted">
                You have {coupons.data.length === 1 ? "a coupon" : "coupons"}:{" "}
                {coupons.data.map((c, k) => (
                  <span key={c.id}>
                    {k > 0 && ", "}
                    <button
                      type="button"
                      className="num font-medium text-brand-ink hover:underline"
                      onClick={() => (setCode(c.coupon_code), check.mutate(c.coupon_code))}
                    >
                      {c.coupon_code}
                    </button>
                  </span>
                ))}
              </p>
            )}
          </form>
        </section>

        <aside className="rounded-lg border border-line bg-surface p-5">
          <h2 className="text-[16px] font-semibold text-ink">Payment</h2>
          <Notice tone="info" className="mt-3">
            This is a demonstration site: the payment is simulated, nothing is charged and no card details are asked
            for.
          </Notice>
          {pay.isError && (
            <Notice tone="bad" className="mt-3">
              {errorText(pay.error)}
            </Notice>
          )}
          <Button
            variant="primary"
            size="lg"
            className="mt-4 w-full"
            icon={<Lock aria-hidden className="size-4" />}
            loading={pay.isPending}
            onClick={() => pay.mutate()}
          >
            Pay {money(total)}
          </Button>
          <p className="mt-3 text-[13px] text-muted">
            Full refund within 7 days of enrolling. A receipt is emailed to you.
          </p>
        </aside>
      </div>
    </div>
  );
}
