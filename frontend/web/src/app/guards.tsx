import { Spinner } from "@xedu/shared/ui";
import { Navigate, Outlet, useLocation } from "react-router";
import { useSession } from "./session";

/** Pages for signed-in learners: the sign-in page first, then back here. */
export function RequireLearner() {
  const { me, checking } = useSession();
  const location = useLocation();
  if (checking) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Spinner label="Opening your account" />
      </div>
    );
  }
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}
