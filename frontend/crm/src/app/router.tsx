import type { ComponentType } from "react";
import { PageLoader } from "@xedu/shared/ui";
import { createBrowserRouter } from "react-router";
import { RouteError } from "../components/RouteError";
import { Shell } from "../components/Shell";
import { Home, RequireRole, RequireSession } from "./guards";

/** Each page is loaded when it is first opened. */
const page = (load: () => Promise<{ default: ComponentType }>) => async () => ({ Component: (await load()).default });

export const router = createBrowserRouter([
  {
    path: "/login",
    lazy: page(() => import("../pages/Login")),
    errorElement: <RouteError />,
    hydrateFallbackElement: <PageLoader />,
  },
  {
    element: <RequireSession />,
    errorElement: <RouteError />,
    hydrateFallbackElement: <PageLoader />,
    children: [
      {
        element: <Shell />,
        errorElement: <RouteError />,
        children: [
          { index: true, element: <Home /> },
          { path: "start", lazy: page(() => import("../pages/Start")) },
          { path: "actions", lazy: page(() => import("../pages/Actions")) },
          { path: "leads", lazy: page(() => import("../pages/Leads")) },
          { path: "leads/:leadId", lazy: page(() => import("../pages/LeadDetail")) },
          { path: "pipeline", lazy: page(() => import("../pages/Pipeline")) },
          { path: "callbacks", lazy: page(() => import("../pages/Callbacks")) },
          { path: "questions", lazy: page(() => import("../pages/Questions")) },
          { path: "campaigns", lazy: page(() => import("../pages/Campaigns")) },
          { path: "ab-tests", lazy: page(() => import("../pages/AbTests")) },
          { path: "ab-tests/:testId", lazy: page(() => import("../pages/AbTestDetail")) },
          { path: "coupons", lazy: page(() => import("../pages/Coupons")) },
          { path: "overview", lazy: page(() => import("../pages/Overview")) },
          { path: "decisions", lazy: page(() => import("../pages/Decisions")) },
          { path: "planner", lazy: page(() => import("../pages/Planner")) },
          { path: "learning", lazy: page(() => import("../pages/Learning")) },
          { path: "model", lazy: page(() => import("../pages/ModelHealth")) },
          { path: "journeys", lazy: page(() => import("../pages/Journeys")) },
          { path: "ask", lazy: page(() => import("../pages/Ask")) },
          {
            element: <RequireRole area="team" />,
            children: [{ path: "team", lazy: page(() => import("../pages/Team")) }],
          },
          {
            element: <RequireRole area="audit" />,
            children: [{ path: "audit", lazy: page(() => import("../pages/Audit")) }],
          },
          { path: "simulation", lazy: page(() => import("../pages/Simulation")) },
          { path: "account", lazy: page(() => import("../pages/Account")) },
          { path: "*", lazy: page(() => import("../pages/NotFound")) },
        ],
      },
    ],
  },
]);
