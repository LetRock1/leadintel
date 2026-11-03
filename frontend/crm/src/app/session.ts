import { createContext, useContext } from "react";
import type { Me, Member } from "../api/types";

export interface SessionState {
  me: Me | null;
  /** True while the first check of a saved session is running. */
  checking: boolean;
  signIn: (email: string, password: string) => Promise<Member>;
  signOut: () => void;
  can: (area: Me["can"][number]) => boolean;
}

export const SessionContext = createContext<SessionState | null>(null);

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}

/** The signed-in person (only inside the signed-in part of the app). */
export function useMe(): Me {
  const { me } = useSession();
  if (!me) throw new Error("Not signed in");
  return me;
}
