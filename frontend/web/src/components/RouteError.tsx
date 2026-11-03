import { buttonClass } from "@xedu/shared/ui";
import { isRouteErrorResponse, Link, useRouteError } from "react-router";

/** A page that could not be opened: its code failed to load (usually after an update), or it crashed. */
export function RouteError() {
  const error = useRouteError();
  const missing = isRouteErrorResponse(error) && error.status === 404;
  const chunk =
    error instanceof Error &&
    /dynamically imported module|Failed to fetch|Importing a module script failed/i.test(error.message);
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col justify-center px-6 py-16">
      <h1 className="text-[28px] font-semibold text-ink">
        {missing
          ? "This page does not exist"
          : chunk
            ? "This page could not be loaded"
            : "Something went wrong on this page"}
      </h1>
      <p className="mt-2 text-[15px] text-muted">
        {missing
          ? "The address may be mistyped, or the page has moved."
          : chunk
            ? "The site was probably updated while you had it open. Reload to get the new version."
            : "Reload the page. If it happens again, please tell us through the help assistant."}
      </p>
      <div className="mt-6 flex gap-2">
        <button type="button" className={buttonClass("primary")} onClick={() => window.location.reload()}>
          Reload
        </button>
        <Link to="/" className={buttonClass("secondary")}>
          Go to the home page
        </Link>
      </div>
    </div>
  );
}
