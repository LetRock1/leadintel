// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { RequireRole } from "./guards";
import { SessionContext, type SessionState } from "./session";

afterEach(cleanup);

function session(role: Me["role"], can: Me["can"]): SessionState {
  return {
    me: { id: 1, name: "Test", email: "t@example.com", role, can } as unknown as Me,
    checking: false,
    signIn: async () => {
      throw new Error("not used");
    },
    signOut: () => {},
    can: (area) => can.includes(area),
  };
}

function open(path: string, s: SessionState) {
  const router = createMemoryRouter(
    [
      {
        element: <RequireRole area="team" />,
        children: [{ path: "/team", element: <p>Team page with Add an account</p> }],
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <SessionContext.Provider value={s}>
      <RouterProvider router={router} />
    </SessionContext.Provider>,
  );
}

describe("RequireRole", () => {
  it("shows an admin page to an admin", () => {
    open("/team", session("admin", ["team", "audit", "marketing", "leads"]));
    expect(screen.getByText("Team page with Add an account")).toBeTruthy();
  });

  it("tells a counsellor the page is not part of their role, and offers their start page", () => {
    open("/team", session("counsellor", ["leads"]));
    expect(screen.queryByText("Team page with Add an account")).toBeNull();
    expect(screen.getByText("This page is not part of your role")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to your start page" }).getAttribute("href")).toBe("/actions");
  });
});
