import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setSignedOutHandler, setToken } from "../api/client";
import type { SignInResponse } from "../api/types";
import { adoptVisit, forgetVisit } from "../lib/tracker";
import { SessionContext, type Me, type SessionState } from "./session";

/** The signed-in learner: the token in this browser, and who it belongs to (GET /auth/me). */
export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [hasToken, setHasToken] = useState(() => Boolean(getToken()));
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<Me>("/auth/me"),
    enabled: hasToken,
    staleTime: 60_000,
  });

  const signOut = useCallback(() => {
    setToken(null);
    forgetVisit();
    setHasToken(false);
    qc.clear();
  }, [qc]);

  useEffect(() => setSignedOutHandler(signOut), [signOut]);

  useEffect(() => {
    const handleAuthChange = () => {
      setHasToken(Boolean(getToken()));
      void qc.invalidateQueries({ queryKey: ["me"] });
    };
    window.addEventListener("xe-auth-changed", handleAuthChange);
    return () => window.removeEventListener("xe-auth-changed", handleAuthChange);
  }, [qc]);

  const adopt = useCallback(
    async (r: SignInResponse) => {
      setToken(r.token);
      adoptVisit(r.session_id);
      setHasToken(true);
      await qc.invalidateQueries();
    },
    [qc],
  );

  const signIn = useCallback(
    async (email: string, password: string) => {
      const r = await api.post<SignInResponse>("/auth/login", { email, password });
      await adopt(r);
      return r;
    },
    [adopt],
  );

  const value = useMemo<SessionState>(
    () => ({
      me: hasToken ? (me.data ?? null) : null,
      checking: hasToken && me.isPending,
      signIn,
      adopt,
      signOut,
    }),
    [hasToken, me.data, me.isPending, signIn, adopt, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
