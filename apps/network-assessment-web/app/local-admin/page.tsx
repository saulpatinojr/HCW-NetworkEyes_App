"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

// Break-glass local admin sign-in. Deliberately unlinked from /auth/signin
// and any nav — only reachable if you already know the URL. Password-only
// (no username field): there's exactly one local admin identity, so asking
// for a username would only invite account-name enumeration.
export default function LocalAdminPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch("/api/local-admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (res.ok) {
        // The session cookie is set by the response; a router navigation
        // re-renders the server components with it.
        router.push("/dashboard");
        return;
      }

      if (res.status === 429) {
        setError("Too many attempts. Try again later.");
      } else {
        setError("Invalid password.");
      }
    } catch {
      setError("Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="glass w-full max-w-sm p-8">
        <h1 className="mb-1 text-2xl font-black tracking-tight text-navy-800 dark:text-navy-50">
          Local Admin Access
        </h1>
        <p className="mb-8 text-sm text-navy-400 dark:text-navy-200">
          Break-glass access for use only when Entra ID SSO is unavailable.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label htmlFor="local-admin-password" className="sr-only">
            Password
          </label>
          <input
            id="local-admin-password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            aria-label="Password"
            className="w-full rounded border border-navy-200 bg-white/60 px-3 py-2 text-sm text-navy-800 dark:border-navy-700 dark:bg-navy-900/60 dark:text-navy-50"
          />

          {error && (
            <p className="text-sm text-red-600 dark:text-red-400" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn-teal w-full justify-center py-2.5 text-sm disabled:opacity-50"
          >
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
