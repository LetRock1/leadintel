import { useEffect } from "react";
import { Link, Outlet, ScrollRestoration, useLocation, useNavigate } from "react-router";
import { useEndSessionOnArrival, useSession } from "../app/session";
import { keepVisitAlive, reportEmailClick } from "../lib/tracker";
import { Assistant } from "./Assistant";
import { Brand, SiteHeader } from "./SiteHeader";

function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line bg-surface print:hidden">
      <div className="mx-auto grid grid-cols-1 max-w-[1200px] gap-8 px-5 py-10 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <Brand />
          <p className="mt-3 max-w-sm text-[13.5px] text-muted">
            Online programmes for people who want to grow in their work, with live sessions every week and a counsellor
            when you need one.
          </p>
        </div>
        <nav aria-label="Courses">
          <h2 className="font-sans text-[13px] font-semibold text-ink">Learn</h2>
          <ul className="mt-2 flex flex-col gap-1.5 text-[14px]">
            <li>
              <Link to="/courses" className="text-ink-2 hover:text-ink">
                All courses
              </Link>
            </li>
            <li>
              <a href="/#live-session" className="text-ink-2 hover:text-ink">
                Free live session
              </a>
            </li>
            <li>
              <Link to="/my-learning" className="text-ink-2 hover:text-ink">
                My learning
              </Link>
            </li>
          </ul>
        </nav>
        <nav aria-label="About this site">
          <h2 className="font-sans text-[13px] font-semibold text-ink">This site</h2>
          <ul className="mt-2 flex flex-col gap-1.5 text-[14px]">
            <li>
              <Link to="/privacy" className="text-ink-2 hover:text-ink">
                Privacy and your data
              </Link>
            </li>
            <li>
              <Link to="/settings" className="text-ink-2 hover:text-ink">
                Email and call preferences
              </Link>
            </li>
          </ul>
        </nav>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-[1200px] px-5 py-4 text-[12.5px] text-muted sm:px-8">
          X Education is a demonstration site for a research project. Payments are simulated and nothing is charged.
          When you are signed in, the pages you visit are recorded to suggest courses; see Privacy.
        </p>
      </div>
    </footer>
  );
}

/** Every page: header, content, footer, the help assistant, and the visit tracking for signed-in learners. */
export function Layout() {
  const { me } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const userId = me?.user.id;

  useEffect(() => (userId ? keepVisitAlive() : undefined), [userId]);
  // a deliberate sign-out (useSignOutHome) ends the session here, once the page it opened is on screen
  useEndSessionOnArrival();

  // an email's button: /courses/<slug>?ref=<token>. The click is reported once and the token taken out of the address.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const ref = params.get("ref");
    if (!ref) return;
    void reportEmailClick(ref);
    params.delete("ref");
    const rest = params.toString();
    navigate({ pathname: location.pathname, search: rest ? `?${rest}` : "", hash: location.hash }, { replace: true });
  }, [location.search, location.pathname, location.hash, navigate]);

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded-sm focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to the content
      </a>
      <SiteHeader />
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <SiteFooter />
      <div className="print:hidden">
        <Assistant />
      </div>
      <ScrollRestoration />
    </div>
  );
}
