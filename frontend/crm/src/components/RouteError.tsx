import { ApiError } from "@xedu/shared/lib";
import { buttonClass } from "@xedu/shared/ui";
import { isRouteErrorResponse, Link, useRouteError } from "react-router";

/** Shown when a page cannot be opened: the page's code failed to load, or the page crashed while drawing. */
export function RouteError() {
  const error = useRouteError();
  const missing = isRouteErrorResponse(error) && error.status === 404;
  const chunk =
    error instanceof Error &&
    /dynamically imported module|Failed to fetch|Importing a module script failed/i.test(error.message);
  const title = missing
    ? "This page does not exist"
    : chunk
      ? "This page could not be loaded"
      : "This page stopped working";
  const detail = missing
    ? "Check the address, or go back to the start."
    : chunk
      ? "The CRM was probably updated while it was open. Reload to get the new version."
      : error instanceof ApiError
        ? error.message
        : "Reload the page. If it happens again, the error is in the browser console and the backend log.";
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col justify-center px-6 py-16">
      <h1 className="text-[22px] font-semibold text-ink">{title}</h1>
      <p className="mt-2 text-[14px] text-muted">{detail}</p>
      <div className="mt-6 flex gap-2">
        <button type="button" className={buttonClass("primary")} onClick={() => window.location.reload()}>
          Reload
        </button>
        <Link to="/" className={buttonClass("secondary")}>
          Go to the start
        </Link>
      </div>
    </div>
  );
}
