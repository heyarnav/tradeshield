"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ErrorNote, Field } from "@/components/ui";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(email, password, fullName);
      router.push("/dashboard");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError(0, "UNKNOWN", "Registration failed. Please try again."),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-md">
      <div className="card-pad animate-fade-up">
        <h1 className="text-xl font-semibold tracking-tight">Create your account</h1>
        <p className="mt-1 text-sm text-mute">
          You get a trading account with $100,000 of simulated cash and an empty portfolio.
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <Field label="Full name">
            <input
              className="input"
              required
              minLength={2}
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Aarav Mehta"
            />
          </Field>
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
          <Field label="Password" hint="At least 8 characters">
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="********"
            />
          </Field>

          {error && <ErrorNote message={error.message} />}

          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? "Creating account>>" : "Create account"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-mute">
          Already registered?{" "}
          <Link href="/login" className="text-brand-soft hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
