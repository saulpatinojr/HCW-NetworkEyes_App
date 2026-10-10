import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import Link from "next/link";
import { StatusBadge } from "@/components/ui/status-badge";
import { DeleteEngagementButton } from "@/components/ui/delete-engagement-button";

type DashboardEngagement = {
  id: string;
  name: string;
  clientOrg: string;
  status: string;
  updatedAt: Date;
  _count: {
    findings: number;
    documents: number;
  };
};

export default async function DashboardPage() {
  const session = await auth();

  const engagements: DashboardEngagement[] = await prisma.engagement.findMany({
    where: { members: { some: { userId: session!.user!.id! } } },
    include: { _count: { select: { findings: true, documents: true } } },
    orderBy: { updatedAt: "desc" },
  });

  const activeCount = engagements.filter(
    (e) => e.status !== "DELIVERED" && e.status !== "DRAFT",
  ).length;

  return (
    <div>
      {/* ── Page header ── */}
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h2 className="label-caps text-navy-400 dark:text-navy-300">
            CBTS Cloud Network Assessment
          </h2>
          <h1 className="mt-1 text-3xl font-black tracking-tight text-navy-800 dark:text-navy-50">
            Engagements
          </h1>
          {engagements.length > 0 && (
            <p className="mt-1.5 text-sm text-navy-400 dark:text-navy-300">
              {engagements.length} total · {activeCount} in progress
            </p>
          )}
        </div>
        <Link href="/engagements/new" className="btn-teal">
          <svg aria-hidden="true" focusable="false" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New engagement
        </Link>
      </div>

      {/* ── Empty state ── */}
      {engagements.length === 0 && (
        <div className="glass flex flex-col items-center gap-4 py-20 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-50 dark:bg-teal-900/40">
            <svg aria-hidden="true" focusable="false" className="h-7 w-7 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <p className="text-base font-semibold text-navy-700 dark:text-navy-100">
              No engagements yet
            </p>
            <p className="mt-1 text-sm text-navy-400 dark:text-navy-300">
              Create an engagement to start a Cloud Network Assessment.
            </p>
          </div>
          <Link href="/engagements/new" className="btn-teal mt-2">
            Create first engagement
          </Link>
        </div>
      )}

      {/* ── Bento engagement grid ── */}
      {engagements.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {engagements.map((eng) => (
            <div
              key={eng.id}
              className="glass glass-hover group relative flex flex-col overflow-hidden"
            >
              {/* Teal accent strip */}
              <div className="h-1 w-full bg-gradient-to-r from-teal-500 to-teal-400 opacity-70 group-hover:opacity-100 transition-opacity" />

              <div className="flex flex-1 flex-col p-5">
                {/* Header row */}
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-lg font-bold leading-snug text-navy-800 dark:text-navy-50">
                      {eng.name}
                    </p>
                    <p className="mt-0.5 truncate text-sm text-navy-400 dark:text-navy-300">
                      {eng.clientOrg}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <StatusBadge value={eng.status} variant="status" />
                    <div className="z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                      <DeleteEngagementButton
                        engagementId={eng.id}
                        engagementName={eng.name}
                        variant="inline"
                      />
                    </div>
                  </div>
                </div>

                {/* Stats row */}
                <div className="mt-auto flex items-center gap-3 pt-3 border-t border-navy-100/50 dark:border-navy-700/50">
                  <div className="flex items-center gap-1.5 text-xs text-navy-400 dark:text-navy-300">
                    <svg aria-hidden="true" focusable="false" className="h-3.5 w-3.5 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                    </svg>
                    <span className="font-semibold text-navy-700 dark:text-navy-100">{eng._count.findings}</span> findings
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-navy-400 dark:text-navy-300">
                    <svg aria-hidden="true" focusable="false" className="h-3.5 w-3.5 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <span className="font-semibold text-navy-700 dark:text-navy-100">{eng._count.documents}</span> docs
                  </div>
                  <p className="ml-auto text-xs text-navy-400 dark:text-navy-300">
                    {new Date(eng.updatedAt).toLocaleDateString()}
                  </p>
                </div>
              </div>

              {/* Full-card link */}
              <Link
                href={`/engagements/${eng.id}`}
                className="absolute inset-0 z-0"
                aria-label={`Open ${eng.name}`}
              />
            </div>
          ))}

          {/* "New" tile */}
          <Link
            href="/engagements/new"
            className="glass glass-hover flex flex-col items-center justify-center gap-3 py-14 text-center opacity-60 hover:opacity-100"
          >
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl border-2 border-dashed border-teal-400 dark:border-teal-600">
              <svg aria-hidden="true" focusable="false" className="h-6 w-6 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-navy-500 dark:text-navy-300">
              New engagement
            </p>
          </Link>
        </div>
      )}
    </div>
  );
}
