import { buttonClass } from "@xedu/shared/ui";
import { CheckCircle2 } from "lucide-react";
import { Link, Navigate, useLocation } from "react-router";
import type { CheckoutResult } from "../api/types";

export default function ThankYou() {
  const r = useLocation().state as CheckoutResult | null;
  if (!r) return <Navigate to="/my-learning" replace />;
  return (
    <div className="mx-auto max-w-[640px] px-5 py-16 sm:px-8">
      <CheckCircle2 aria-hidden className="size-9 text-good" />
      <h1 className="mt-4 text-[32px] font-semibold leading-tight text-ink">You are enrolled</h1>
      <p className="mt-3 text-[16px] text-ink-2">
        {r.courses_purchased.join(" and ")} {r.courses_purchased.length === 1 ? "is" : "are"} now in My learning.
        {r.confirmation_emailed && " A confirmation is on its way to your email."}
      </p>
      {r.discount_applied !== "None" && (
        <p className="mt-2 text-[15px] text-muted">Your coupon took {r.discount_applied} off.</p>
      )}
      {r.demo_payment !== false && (
        <p className="mt-2 text-[14px] text-muted">This site takes no real payments: nothing was charged.</p>
      )}
      <div className="mt-8 flex flex-wrap gap-2">
        <Link to="/my-learning" className={buttonClass("primary", "lg")}>
          Go to my learning
        </Link>
        <a href="/#live-session" className={buttonClass("secondary", "lg")}>
          Join the Saturday session
        </a>
      </div>
    </div>
  );
}
