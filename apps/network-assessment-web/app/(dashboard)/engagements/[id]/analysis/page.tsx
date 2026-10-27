import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import { AiAnalysisForm } from "../findings/ai-analysis-form";
import { ComplianceReportPanel } from "../documents/compliance-report-panel";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function AnalysisPage({ params }: PageProps) {
  const { id } = await params;
  const session = await auth();

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    select: { id: true, members: true },
  });
  if (!engagement) notFound();
  const isMember = engagement.members.some((m) => m.userId === session?.user?.id);
  if (!isMember) notFound();

  let hasTopology = false;
  let hasDocumentsParsed = false;
  try {
    const [job, docCount] = await Promise.all([
      prisma.discoveryJob.findFirst({
        where: { engagementId: id, status: "COMPLETED" },
        select: { id: true },
      }),
      prisma.ingestedDocument.count({
        where: { engagementId: id, parsedText: { not: null } },
      }),
    ]);
    hasTopology = !!job;
    hasDocumentsParsed = docCount > 0;
  } catch { /* migration pending */ }

  // Compute "needs resync" warning: any credential that has never had a completed sync,
  // or whose updatedAt is newer than its latest completed job.
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

  const hasAnalysisData = hasTopology || hasDocumentsParsed;

  return (
    <div className="space-y-6">
      {needsResync && hasTopology && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-700/40 bg-amber-50 dark:bg-amber-900/20 px-4 py-3">
          <svg className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm0-2a6 6 0 110-12 6 6 0 010 12zm-1-9a1 1 0 112 0v4a1 1 0 11-2 0V7zm0 6a1 1 0 112 0 1 1 0 01-2 0z" clipRule="evenodd" />
          </svg>
          <p className="text-sm text-amber-700 dark:text-amber-300">
            <span className="font-semibold">Subscriptions changed</span> — re-sync on the Connections tab before running analysis to ensure findings reflect the current inventory.
          </p>
        </div>
      )}

      {/* ── AI Analysis ── */}
      <section className="glass p-6">
        <h2 className="mb-1 text-lg font-semibold text-navy-800 dark:text-navy-100">AI Analysis</h2>
        <p className="mb-4 text-sm text-navy-400">
          Run a focused security analysis on your discovered topology and uploaded
          documents. Each focus type uses a different analytical lens. Results are
          added to the Findings tab.
        </p>
        {!hasAnalysisData ? (
          <p className="rounded-lg border border-amber-800/40 bg-amber-50 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-600 dark:text-amber-400">
            No data to analyze yet. Run discovery on the Connections tab to capture live
            topology, or upload documents on the Documents tab.
          </p>
        ) : (
          <AiAnalysisForm engagementId={id} />
        )}
      </section>

      {/* ── Compliance Check ── */}
      <ComplianceReportPanel engagementId={id} hasTopology={hasTopology} needsResync={needsResync} />
    </div>
  );
}
