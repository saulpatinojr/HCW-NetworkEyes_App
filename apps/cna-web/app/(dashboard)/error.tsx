"use client";

// Route-segment error boundary for all dashboard pages. Renders inside the
// dashboard layout (header/nav stay up) and surfaces the error digest so it
// can be matched against the server-side onRequestError log line.
import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[dashboard error boundary]", error.digest ?? "", error);
  }, [error]);

  return (
    <div className="glass mx-auto mt-16 max-w-lg rounded-xl p-8 text-center">
      <h1 className="text-lg font-black text-navy-800 dark:text-navy-100">
        Something went wrong loading this page
      </h1>
      <p className="mt-2 text-sm text-navy-400">
        The error has been logged on the server. Try again, or share the
        reference below with your administrator.
      </p>
      {error.digest && (
        <p className="mt-3 font-mono text-xs text-navy-500">
          Error reference: {error.digest}
        </p>
      )}
      <button
        onClick={reset}
        className="mt-6 rounded-lg bg-teal-600 px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-teal-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1"
      >
        Try again
      </button>
    </div>
  );
}
