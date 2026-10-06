"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { api, setToken, getToken, ApiError } from "./api";
import type { AccountSummary, User } from "./types";

interface AuthContextValue {
  user: User | null;
  account: AccountSummary | null;
  ready: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (
    email: string,
    password: string,
    fullName: string,
  ) => Promise<{ user: User; account: AccountSummary }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [ready, setReady] = useState(false);

  // Restore the session from a stored token on first load.
  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    if (!token) {
      setReady(true);
      return;
    }
    api<{ user: User; account: AccountSummary | null }>("/auth/me")
      .then((data) => {
        if (cancelled) return;
        setUser(data.user);
        setAccount(data.account);
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.code === "INVALID_TOKEN") {
          setToken(null);
        }
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The API client emits this when a token expires mid-session.
  useEffect(() => {
    const onUnauthorized = () => {
      setToken(null);
      setUser(null);
      setAccount(null);
      router.push("/login");
    };
    window.addEventListener("ts:unauthorized", onUnauthorized);
    return () => window.removeEventListener("ts:unauthorized", onUnauthorized);
  }, [router]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api<{ token: string; user: User }>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setToken(data.token);
    setUser(data.user);
    // The session is already valid at this point; a failure here (e.g. a brief
    // network drop) must not turn a successful login into an error page. The
    // app shell re-reads /auth/me on mount and retries.
    try {
      const me = await api<{ account: AccountSummary | null }>("/auth/me");
      setAccount(me.account);
    } catch (error) {
      console.warn("login succeeded but /auth/me failed", error);
    }
    return data.user;
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const data = await api<{
        token: string;
        user: User;
        account: AccountSummary;
      }>("/auth/register", {
        method: "POST",
        body: { email, password, full_name: fullName },
      });
      setToken(data.token);
      setUser(data.user);
      setAccount(data.account);
      return { user: data.user, account: data.account };
    },
    [],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setAccount(null);
    router.push("/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      account,
      ready,
      isAdmin: user?.role === "admin",
      login,
      register,
      logout,
    }),
    [user, account, ready, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
