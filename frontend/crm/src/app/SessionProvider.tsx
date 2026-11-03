import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setSignedOutHandler, setToken } from "../api/client";
import type { Me, Member } from "../api/types";
import { SessionContext, type SessionState } from "./session";

/** Keeps the signed-in team member: the token in this browser, and who it belongs to (GET /me). */
export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [hasToken, setHasToken] = useState(() => Boolean(getToken()));

  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<Me>("/me"),
    enabled: hasToken,
    staleTime: 60_000,
  });

  const signOut = useCallback(() => {
    setToken(null);
    setHasToken(false);
    qc.clear();
  }, [qc]);

  useEffect(() => setSignedOutHandler(signOut), [signOut]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const r = await api.post<{ token: string; member: Member }>("/auth/login", { email, password });
      setToken(r.token);
      setHasToken(true);
      await qc.invalidateQueries({ queryKey: ["me"] });
      return r.member;
    },
    [qc],
  );

  const value = useMemo<SessionState>(() => {
    const m = hasToken ? (me.data ?? null) : null;
    return {
      me: m,
      checking: hasToken && me.isPending,
      signIn,
      signOut,
      can: (area) => Boolean(m?.can.includes(area)),
    };
  }, [hasToken, me.data, me.isPending, signIn, signOut]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
