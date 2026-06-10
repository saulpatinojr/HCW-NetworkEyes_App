import { auth, signOut } from "@/lib/auth";
import { redirect } from "next/navigation";
import Link from "next/link";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) redirect("/auth/signin");

  const email = session.user.email ?? "";
  const initial = email.charAt(0).toUpperCase();

  return (
    <div className="flex min-h-screen flex-col">
      {/* WAI-16: Skip-to-main-content — visible on focus, hidden otherwise */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[200] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-navy-800 focus:shadow-lg focus:ring-2 focus:ring-teal-500 dark:focus:bg-navy-900 dark:focus:text-navy-100"
      >
        Skip to main content
      </a>

      {/* ── Glass header ── */}
      <header className="header-glass sticky top-0 z-50">
        <div className="mx-auto flex max-w-screen-2xl items-center justify-between px-6 py-3">
          {/* Logo + wordmark */}
          <Link href="/dashboard" className="flex items-center gap-3">
            {/* W3C-01 / W3C-12: picture tag with prefers-color-scheme prevents duplicate downloads and CLS */}
            <picture>
              <source
                srcSet="/cbts-logo-bright-teal.svg"
                media="(prefers-color-scheme: dark)"
              />
              <img
                src="/cbts-logo-dark-teal.svg"
                alt="CBTS"
                className="h-8 w-auto"
                width={96}
                height={32}
              />
            </picture>
            <div className="mx-1 h-5 w-px bg-navy-100 dark:bg-navy-700" />
            <span className="hidden text-sm font-semibold tracking-tight text-navy-500 dark:text-navy-200 sm:block">
              Cloud Network Assessment
            </span>
          </Link>

          {/* User controls */}
          <div className="flex items-center gap-3">
            <Link
              href="/admin/ai-engine"
              className="rounded-lg border border-teal-200 bg-teal-50 px-3.5 py-1.5 text-xs font-bold text-teal-700 transition-colors hover:bg-teal-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1 dark:border-teal-800 dark:bg-teal-950 dark:text-teal-300 dark:hover:bg-teal-900"
            >
              AI
            </Link>

            {/* Avatar + email */}
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-100 ring-2 ring-teal-500/25 dark:bg-teal-900">
                <span className="text-xs font-bold text-teal-700 dark:text-teal-300">
                  {initial}
                </span>
              </div>
              <span className="hidden text-sm font-medium text-navy-500 dark:text-navy-200 md:block">
                {email}
              </span>
            </div>

            {/* Sign out */}
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/auth/signin" });
              }}
            >
              <button
                type="submit"
                className="rounded-lg border border-navy-100 bg-white/60 px-3.5 py-1.5 text-xs font-semibold text-navy-600 transition-colors hover:bg-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1 dark:border-navy-700 dark:bg-white/5 dark:text-navy-200 dark:hover:bg-white/10"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>

      {/* ── Page content ── */}
      {/* WAI-16: id="main-content" is the skip-link target */}
      <main id="main-content" className="mx-auto w-full max-w-screen-2xl flex-1 px-6 py-8">
        {children}
      </main>
    </div>
  );
}
