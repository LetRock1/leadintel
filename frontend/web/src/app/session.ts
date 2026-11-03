import { useToast } from "@xedu/shared/ui";
import { createContext, useCallback, useContext, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import type { Profile, SignInResponse, User } from "../api/types";

export interface Me {
  user: User;
  profile: Profile | null;
}

export interface SessionState {
  me: Me | null;
  /** True while a saved session is being checked. */
  checking: boolean;
  signIn: (email: string, password: string) => Promise<SignInResponse>;
  /** Keeps the token of a sign-in that happened elsewhere (verifying the sign-up code). */
  adopt: (r: SignInResponse) => Promise<void>;
  signOut: () => void;
}

export const SessionContext = createContext<SessionState | null>(null);

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}

/** The signed-in learner (only on pages behind RequireLearner). */
export function useMe(): Me {
  const { me } = useSession();
  if (!me) throw new Error("Not signed in");
  return me;
}

/** The history state of the page a deliberate sign-out opens: the session ends once that page is on screen. */
export interface SignOutState {
  signOut: true;
  /** A confirmation to show there. */
  message?: string;
}

/**
 * Sign out on purpose (the account menu, or after deleting the account): open the home page first and end the
 * session once it is on screen (useEndSessionOnArrival, in the Layout), so the signed-in page being left never sees
 * the session end and sends the learner to the sign-in page instead.
 */
export function useSignOutHome(): (message?: string) => void {
  const navigate = useNavigate();
  return useCallback(
    (message?: string) => {
      const state: SignOutState = message ? { signOut: true, message } : { signOut: true };
      void navigate("/", { replace: true, state });
    },
    [navigate],
  );
}

/** Ends the session once the page a deliberate sign-out opened is on screen, and shows its confirmation. */
export function useEndSessionOnArrival(): void {
  const { signOut } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const state = location.state as SignOutState | null;
  const leaving = state?.signOut === true;
  const message = leaving ? state?.message : undefined;
  // each history entry is handled once, even if the effect runs again before the entry is replaced
  const handled = useRef<string | null>(null);
  useEffect(() => {
    if (!leaving || handled.current === location.key) return;
    handled.current = location.key;
    signOut();
    if (message) toast({ tone: "good", text: message });
    // the history entry forgets the sign-out, so going back and forward does not repeat it
    void navigate({ pathname: location.pathname, search: location.search, hash: location.hash }, { replace: true });
  }, [leaving, message, signOut, toast, navigate, location.key, location.pathname, location.search, location.hash]);
}
