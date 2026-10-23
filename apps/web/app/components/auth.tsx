"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { request } from "../lib/client";
import type { AccountUser } from "../lib/auth-helpers";

type Status = "loading" | "ready";
type AuthValue = {
  user: AccountUser | null;
  status: Status;
  /** Replace the cached user, e.g. with the response from a sign-in call. */
  setUser: (user: AccountUser | null) => void;
  refresh: () => Promise<AccountUser | null>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthValue>({ user: null, status: "loading", setUser: () => {}, refresh: async () => null, signOut: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AccountUser | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const refresh = useCallback(async () => {
    try {
      const { user: next } = await request<{ user: AccountUser | null }>("/api/auth/me");
      setUser(next);
      return next;
    } catch { return null; }
    finally { setStatus("ready"); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const signOut = useCallback(async () => {
    try { await request("/api/auth/logout", { method: "POST", body: {} }); } catch { /* The cookie may already be gone. */ }
    setUser(null);
  }, []);
  const value = useMemo(() => ({ user, status, setUser, refresh, signOut }), [user, status, refresh, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
