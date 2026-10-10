import Link from "next/link";

// Branded 404 surface (UI-004). Next.js renders this for notFound() and for
// unmatched routes. Engagement routes also call notFound() for access-denied
// (non-member) targets, so the copy is deliberately non-enumerating: it does not
// reveal whether the resource exists, only that it is unavailable to this user.
export const metadata = {
  title: "Not found — CNA Platform",
};

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="glass w-full max-w-md p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-navy-100 dark:bg-navy-800">
          <svg
            aria-hidden="true"
            focusable="false"
            className="h-6 w-6 text-teal-600 dark:text-teal-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z"
            />
          </svg>
        </div>
        <p className="text-sm font-semibold uppercase tracking-[0.12em] text-teal-700 dark:text-teal-400">
          404
        </p>
        <h1 className="mt-1 mb-2 text-2xl font-black tracking-tight text-navy-800 dark:text-navy-50">
          Page not available
        </h1>
        <p className="mx-auto mb-6 max-w-sm text-sm text-navy-400 dark:text-navy-300">
          This page does not exist, or you do not have access to it. Check the
          link, or head back to your dashboard.
        </p>
        <Link href="/dashboard" className="btn-teal inline-flex justify-center">
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
