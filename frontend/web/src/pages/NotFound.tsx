import { buttonClass } from "@xedu/shared/ui";
import { Link } from "react-router";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-[640px] px-5 py-20 sm:px-8">
      <h1 className="text-[32px] font-semibold text-ink">This page does not exist</h1>
      <p className="mt-3 text-[16px] text-ink-2">The address may be mistyped, or the page has moved.</p>
      <div className="mt-6 flex gap-2">
        <Link to="/courses" className={buttonClass("primary", "lg")}>
          See all courses
        </Link>
        <Link to="/" className={buttonClass("secondary", "lg")}>
          Home
        </Link>
      </div>
    </div>
  );
}
