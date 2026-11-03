import { buttonClass, EmptyState, Spinner } from "@xedu/shared/ui";
import { Lock } from "lucide-react";
import { Link, Navigate, Outlet, useLocation } from "react-router";
import type { Me } from "../api/types";
import { useSession } from "./session";

/** The signed-in part of the CRM: a spinner while a saved session is checked, the sign-in page without one. */
export function RequireSession() {
  const { me, checking } = useSession();
  const location = useLocation();
  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Opening the CRM" />
      </div>
    );
  }
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (me.must_change_password && location.pathname !== "/account") return <Navigate to="/account" replace />;
  return <Outlet />;
}

/** The start page: counsellors start with their tasks, everyone else with the overview. */
export function Home() {
  const { me } = useSession();
  return <Navigate to={me?.role === "counsellor" ? "/actions" : "/overview"} replace />;
}

const WHO: Record<Me["can"][number], string> = {
  team: "admins",
  audit: "admins",
  marketing: "admins and marketing",
  leads: "the team",
};

/** A page only some roles may use (opened from an old link or typed in): a plain message instead of a broken page.
 * The API refuses the data anyway; this keeps the screen honest. */
export function RequireRole({ area }: { area: Me["can"][number] }) {
  const { can, me } = useSession();
  if (can(area)) return <Outlet />;
  return (
    <div className="rounded-md border border-line bg-surface px-4">
      <EmptyState
        icon={Lock}
        title="This page is not part of your role"
        action={
          <Link to={me?.role === "counsellor" ? "/actions" : "/overview"} className={buttonClass("secondary", "sm")}>
            Back to your start page
          </Link>
        }
      >
        It is for {WHO[area]}. Ask an admin if you need something on it.
      </EmptyState>
    </div>
  );
}
