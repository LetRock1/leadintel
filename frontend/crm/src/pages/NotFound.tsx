import { buttonClass } from "@xedu/shared/ui";
import { Link } from "react-router";

export default function NotFound() {
  return (
    <div className="max-w-lg py-16">
      <h1 className="text-[22px] font-semibold text-ink">This page does not exist</h1>
      <p className="mt-2 text-[14px] text-muted">The address may be mistyped, or the page has moved.</p>
      <Link to="/" className={buttonClass("primary", "md", "mt-6")}>
        Go to the start
      </Link>
    </div>
  );
}
