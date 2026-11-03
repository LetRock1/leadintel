import type { ComponentType } from "react";
import { PageLoader } from "@xedu/shared/ui";
import { createBrowserRouter } from "react-router";
import { Layout } from "../components/Layout";
import { RouteError } from "../components/RouteError";
import { RequireLearner } from "./guards";

/** Each page is loaded when it is first opened. */
const page = (load: () => Promise<{ default: ComponentType }>) => async () => ({ Component: (await load()).default });

export const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: <RouteError />,
    hydrateFallbackElement: <PageLoader />,
    children: [
      {
        errorElement: <RouteError />,
        children: [
          { index: true, lazy: page(() => import("../pages/Home")) },
          { path: "courses", lazy: page(() => import("../pages/Courses")) },
          { path: "courses/:slug", lazy: page(() => import("../pages/CourseDetail")) },
          { path: "courses/:slug/brochure", lazy: page(() => import("../pages/Brochure")) },
          { path: "signup", lazy: page(() => import("../pages/Signup")) },
          { path: "verify", lazy: page(() => import("../pages/Verify")) },
          { path: "login", lazy: page(() => import("../pages/Login")) },
          { path: "forgot-password", lazy: page(() => import("../pages/ForgotPassword")) },
          { path: "reset-password", lazy: page(() => import("../pages/ResetPassword")) },
          { path: "unsubscribe", lazy: page(() => import("../pages/Unsubscribe")) },
          { path: "privacy", lazy: page(() => import("../pages/Privacy")) },
          {
            element: <RequireLearner />,
            children: [
              { path: "welcome", lazy: page(() => import("../pages/Welcome")) },
              { path: "my-learning", lazy: page(() => import("../pages/MyLearning")) },
              { path: "wishlist", lazy: page(() => import("../pages/Wishlist")) },
              { path: "cart", lazy: page(() => import("../pages/Cart")) },
              { path: "checkout", lazy: page(() => import("../pages/Checkout")) },
              { path: "thank-you", lazy: page(() => import("../pages/ThankYou")) },
              { path: "enquiry/:slug", lazy: page(() => import("../pages/Enquiry")) },
              { path: "settings", lazy: page(() => import("../pages/Settings")) },
            ],
          },
          { path: "*", lazy: page(() => import("../pages/NotFound")) },
        ],
      },
    ],
  },
]);
