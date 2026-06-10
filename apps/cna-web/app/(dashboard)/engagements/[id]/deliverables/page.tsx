import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import { deleteDeliverable } from "./actions";
import { GenerateDeliverableForm } from "./generate-form";

interface PageProps {
  params: Promise<{ id: string }>;
}

const TYPE_META: Record<string, { label: string; icon: string; audience: string }> = {
  COMPREHENSIVE_ASSESSMENT: {
    label: "Comprehensive Assessment",
    audience: "All Stakeholders",
    icon: "M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  },
  EXECUTIVE_SUMMARY: {
    label: "Executive Summary",
    audience: "CxO / CISO / Board",
    icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  },
  TECHNICAL_FINDINGS: {
    label: "Technical Findings",
    audience: "Security Engineers",
    icon: "M10 21h7a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v11m0 5l4.879-4.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242z",
  },
  REMEDIATION_PLAN: {
    label: "Remediation Plan",
    audience: "IT / Platform Team",
    icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4",
  },
  SPECIALIZATION_REPORT: {
    label: "Specialization Report",
    audience: "Security Architect / Compliance",
    icon: "M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z",
  },
  ENCYCLOPEDIA_CONDENSED: {
    label: "Networking Encyclopedia — Condensed",
    audience: "Executive Sponsors",
    icon: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
  },
  ENCYCLOPEDIA_EXPANDED: {
    label: "Networking Encyclopedia — Expanded",
    audience: "All Stakeholders",
    icon: "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
  },
};

export default async function AssessmentsPage({ params }: PageProps) {
  const { id } = await params;
  const session = await auth();

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    select: {
      id: true,
      members: true,
      deliverables: {
        orderBy: { createdAt: "desc" },
        select: {
          id: true,
          title: true,
          type: true,
          createdAt: true,
          publishedAt: true,
        },
      },
      findings: { select: { id: true } },
    },
  });
  if (!engagement) notFound();
  const isMember = engagement.members.some((m) => m.userId === session?.user?.id);
  if (!isMember) notFound();

  const { deliverables, findings } = engagement;

  let needsResync = false;
  try {
    const [credentials, completedJobs] = await Promise.all([
      prisma.cloudCredential.findMany({
        where: { engagementId: id },
        select: { id: true, updatedAt: true },
      }),
      prisma.discoveryJob.findMany({
        where: { engagementId: id, status: "COMPLETED" },
        select: { credentialId: true, completedAt: true },
        orderBy: { completedAt: "desc" },
      }),
    ]);
    if (credentials.length > 0) {
      const latestJobByCredential = new Map<string, Date>();
      for (const job of completedJobs) {
        if (job.credentialId && !latestJobByCredential.has(job.credentialId)) {
          latestJobByCredential.set(job.credentialId, job.completedAt!);
        }
      }
      needsResync = credentials.some((cred) => {
        const lastSync = latestJobByCredential.get(cred.id);
        return !lastSync || cred.updatedAt > lastSync;
      });
    }
  } catch { /* migration pending */ }

  return (
    <div className="space-y-5">
      {/* ── Generate Assessment ── */}
      <div className="glass p-6">
        <h2 className="label-caps mb-1 text-navy-500">Generate Assessment</h2>
        <p className="mb-5 text-xs text-navy-500">
          AI-powered generation using live topology, uploaded documents, and all findings.
          {findings.length === 0 && (
            <span className="ml-2 font-medium text-amber-400">
              No findings yet — run discovery or AI analysis first.
            </span>
          )}
        </p>
        {needsResync && (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-700/40 bg-amber-900/20 px-4 py-3">
            <svg aria-hidden="true" focusable="false" className="h-4 w-4 shrink-0 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm0-2a6 6 0 110-12 6 6 0 010 12zm-1-9a1 1 0 112 0v4a1 1 0 11-2 0V7zm0 6a1 1 0 112 0 1 1 0 01-2 0z" clipRule="evenodd" />
            </svg>
            <p className="text-sm text-amber-300">
              <span className="font-semibold">Subscriptions changed</span> — re-sync on the Connections tab before generating to include the latest inventory.
            </p>
          </div>
        )}
        <GenerateDeliverableForm engagementId={id} />
      </div>

      {/* ── Generated Assessments ── */}
      <div className="glass p-6">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="label-caps text-navy-500">Generated Assessments</h2>
            <p className="mt-0.5 text-xs text-navy-500">
              View assessments in-browser or open them in the Presentation tab.
            </p>
          </div>
          {deliverables.length > 0 && (
            <span className="pill-teal">
              {deliverables.length} assessment{deliverables.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {deliverables.length === 0 ? (
          <div className="rounded-xl border border-dashed border-navy-700 px-6 py-10 text-center">
            <svg aria-hidden="true" focusable="false" className="mx-auto mb-3 h-8 w-8 text-navy-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            <p className="text-sm font-medium text-navy-400">No assessments yet.</p>
            <p className="mt-1 text-xs text-navy-600">Generate one from the form above.</p>
          </div>
        ) : (
          <div className="divide-y divide-navy-700/30">
            {deliverables.map((d) => {
              const meta = TYPE_META[d.type];
              const isHtml =
                d.type === "COMPREHENSIVE_ASSESSMENT" ||
                d.type === "ENCYCLOPEDIA_CONDENSED" ||
                d.type === "ENCYCLOPEDIA_EXPANDED";
              return (
                <div key={d.id} className="flex items-center gap-4 py-4">
                  {/* Icon */}
                  {meta && (
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-900/30">
                      <svg aria-hidden="true" focusable="false" className="h-4 w-4 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d={meta.icon} />
                      </svg>
                    </div>
                  )}

                  {/* Name + meta */}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-navy-100">{d.title}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <span className="rounded border border-navy-700/40 bg-navy-800/40 px-1.5 py-0.5 text-xs text-navy-400">
                        {meta?.audience ?? d.type.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs text-navy-600">
                        {new Date(d.createdAt).toLocaleDateString("en-US", {
                          month: "short", day: "numeric", year: "numeric",
                        })}
                      </span>
                      {d.publishedAt && (
                        <span className="pill-teal">Published</span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 items-center gap-2">
                    <a
                      href={`/api/deliverables/${d.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-navy-600/60 bg-navy-700/40 px-3 py-1.5 text-xs font-medium text-navy-200 transition-colors hover:bg-navy-700/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500"
                    >
                      <svg aria-hidden="true" focusable="false" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d={isHtml
                          ? "M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                          : "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                        } />
                      </svg>
                      {isHtml ? "View / PDF" : "Download"}
                      <span className="sr-only"> (opens in new tab)</span>
                    </a>

                    {/* Delete */}
                    <form action={deleteDeliverable} aria-label={`Delete ${d.title}`}>
                      <input type="hidden" name="deliverableId" value={d.id} />
                      <input type="hidden" name="engagementId" value={id} />
                      <button
                        type="submit"
                        aria-label={`Delete ${d.title}`}
                        className="flex h-7 w-7 items-center justify-center rounded-lg border border-red-800/40 bg-red-900/20 text-red-400 transition-colors hover:bg-red-900/40 hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                      >
                        <svg aria-hidden="true" focusable="false" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </form>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
