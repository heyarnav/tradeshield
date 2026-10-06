"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ErrorNote, Field } from "@/components/ui";

const DEMO_ACCOUNTS = [
  { label: "Client demo", email: "client@tradeshield.dev", password: "Client@123" },
  { label: "Admin demo", email: "admin@tradeshield.dev", password: "Admin@123" },
];

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError(0, "UNKNOWN", "Sign in failed. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-md">
      <div className="card-pad animate-fade-up">
        <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-sm text-mute">
          Access your trading account and the security console.
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <Field label="Email">
            <input
              className="input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </Field>
          <Field label="Password">
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="********"
            />
          </Field>

          {error && <ErrorNote message={error.message} />}

          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? "Signing in>>" : "Sign in"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-mute">
          No account yet?{" "}
          <Link href="/register" className="text-brand-soft hover:underline">
            Create one
          </Link>
        </p>
      </div>

      <div className="card-pad mt-4">
        <p className="section-title">Demo accounts</p>
        <div className="mt-3 space-y-2">
          {DEMO_ACCOUNTS.map((account) => (
            <button
              key={account.email}
              type="button"
              className="btn-ghost w-full justify-between"
              onClick={() => {
                setEmail(account.email);
                setPassword(account.password);
              }}
            >
              <span>{account.label}</span>
              <span className="num text-xs text-mute">{account.email}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
