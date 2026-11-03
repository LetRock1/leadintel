// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ToastProvider } from "@xedu/shared/ui";
import { useMemo, useState, type ReactNode } from "react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { RequireLearner } from "./guards";
import {
  SessionContext,
  useEndSessionOnArrival,
  useSession,
  useSignOutHome,
  type Me,
  type SessionState,
} from "./session";

afterEach(cleanup);

const ME = { user: { id: 7, name: "Asha Rao", email: "asha@example.com" }, profile: null } as unknown as Me;

/** A signed-in learner whose session ends when signOut is called, as in SessionProvider. */
function TestSession({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(ME);
  const value = useMemo<SessionState>(
    () => ({
      me,
      checking: false,
      signIn: () => Promise.reject(new Error("not used")),
      adopt: () => Promise.resolve(),
      signOut: () => setMe(null),
    }),
    [me],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

function Root() {
  useEndSessionOnArrival();
  return <Outlet />;
}

function Home() {
  const { me } = useSession();
  return <p>Home page, {me ? "signed in" : "signed out"}</p>;
}

/** A page behind RequireLearner with both ways a session ends. */
function Cart() {
  const signOutHome = useSignOutHome();
  const { signOut } = useSession();
  return (
    <>
      <button onClick={() => signOutHome("Your account is deleted.")}>Sign out</button>
      <button onClick={signOut}>Session ends</button>
    </>
  );
}

function open(path: string) {
  const router = createMemoryRouter(
    [
      {
        element: <Root />,
        children: [
          { index: true, element: <Home /> },
          { path: "login", element: <p>Sign-in page</p> },
          { element: <RequireLearner />, children: [{ path: "cart", element: <Cart /> }] },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <ToastProvider>
      <TestSession>
        <RouterProvider router={router} />
      </TestSession>
    </ToastProvider>,
  );
  return router;
}

describe("signing out", () => {
  it("on purpose, from a signed-in page, opens the home page and ends the session there", async () => {
    const router = open("/cart");
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("Home page, signed out")).toBeTruthy();
    expect(screen.queryByText("Sign-in page")).toBeNull();
    expect(screen.getByText("Your account is deleted.")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
    // the history entry no longer carries the sign-out, so going back and forward does not repeat it
    expect(router.state.location.state).toBeFalsy();
  });

  it("when the session ends by itself, asks to sign in again and remembers the page", async () => {
    const router = open("/cart");
    fireEvent.click(screen.getByRole("button", { name: "Session ends" }));
    expect(await screen.findByText("Sign-in page")).toBeTruthy();
    expect(router.state.location.state).toEqual({ from: "/cart" });
  });
});
