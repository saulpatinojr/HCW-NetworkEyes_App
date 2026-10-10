"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { analyzeEngagement, type AnalysisFocus } from "@/lib/openai";
import { revalidatePath } from "next/cache";

const ALL_FOCUSES: AnalysisFocus[] = [
  "general",
  "zero_trust",
  "compliance_nist",
  "compliance_cis",
  "well_architected",
  "remediation_priority",
  "traffic_flow",
  "dependency_chains",
  "interconnect",
  "routing_decisions",
  "resilience",
];

export async function runAnalysis(
  _prev: { error?: string; success?: boolean; count?: number } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean; count?: number }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const engagementId = formData.get("engagementId") as string | null;
  const focus = (formData.get("focus") as AnalysisFocus | null) ?? "general";
  if (!engagementId) return { error: "Missing engagement ID." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  // Gather all three data sources in parallel
  const [documents, existingFindings, latestJob] = await Promise.all([
    prisma.ingestedDocument.findMany({
      where: { engagementId, parsedText: { not: null } },
      select: { fileName: true, parsedText: true },
    }),
    prisma.finding.findMany({
      where: { engagementId },
      select: { title: true, severity: true, category: true, description: true },
    }),
    prisma.discoveryJob
      .findFirst({
        where: { engagementId, status: "COMPLETED" },
        orderBy: { completedAt: "desc" },
        select: { topologyJson: true },
      })
      .catch(() => null), // table may not be migrated in all envs
  ]);

  const hasTopology = !!latestJob?.topologyJson;
  const hasDocs = documents.length > 0;

  if (!hasTopology && !hasDocs) {
    return {
      error:
        "No data to analyze. Run a discovery first to capture topology, or upload network documents.",
    };
  }

  let rawFindings;
  try {
    rawFindings = await analyzeEngagement({
      topologyJson: latestJob?.topologyJson ?? null,
      documents: documents.map((d) => ({ fileName: d.fileName, text: d.parsedText! })),
      existingFindings,
      focus,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("[runAnalysis][error]", err);
    if (msg.includes("401") || msg.includes("PermissionDenied") || msg.includes("lacks the required")) {
      return { error: "AI analysis failed: the web app is missing the required 'Cognitive Services User' access on the active AI resource." };
    }
    return { error: "AI analysis failed. Check that the active AI engine is reachable, then try again — the full error has been logged." };
  }

  const existingTitles = new Set(existingFindings.map((f) => f.title.toLowerCase().trim()));
  const newFindings = rawFindings.filter((f) => !existingTitles.has(f.title.toLowerCase().trim()));

  if (newFindings.length > 0) {
    await prisma.finding.createMany({
      data: newFindings.map((f) => ({
        engagementId,
        title: f.title,
        severity: f.severity,
        category: f.category,
        description: f.description,
        recommendation: f.recommendation,
        aiGenerated: true,
      })),
    });
  }

  await prisma.engagement.update({
    where: { id: engagementId },
    data: { status: "ANALYSIS" },
  });

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true, count: newFindings.length };
}

export async function runAllAnalysis(
  _prev: { error?: string; success?: boolean; count?: number } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean; count?: number }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const engagementId = formData.get("engagementId") as string | null;
  if (!engagementId) return { error: "Missing engagement ID." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  // Delete stale AI findings before re-running — gives replace semantics
  await prisma.finding.deleteMany({
    where: { engagementId, aiGenerated: true },
  });

  const [documents, existingFindings, latestJob] = await Promise.all([
    prisma.ingestedDocument.findMany({
      where: { engagementId, parsedText: { not: null } },
      select: { fileName: true, parsedText: true },
    }),
    prisma.finding.findMany({
      where: { engagementId },
      select: { title: true, severity: true, category: true, description: true },
    }),
    prisma.discoveryJob
      .findFirst({
        where: { engagementId, status: "COMPLETED" },
        orderBy: { completedAt: "desc" },
        select: { topologyJson: true },
      })
      .catch(() => null),
  ]);

  if (!latestJob?.topologyJson && documents.length === 0) {
    return { error: "No data to analyze. Run a discovery first or upload documents." };
  }

  const docInput = documents.map((d) => ({ fileName: d.fileName, text: d.parsedText! }));
  const topologyJson = latestJob?.topologyJson ?? null;

  // Run all focuses in parallel; collect any that succeed
  const settled = await Promise.allSettled(
    ALL_FOCUSES.map((focus) =>
      analyzeEngagement({ topologyJson, documents: docInput, existingFindings, focus }),
    ),
  );

  const allRaw = settled.flatMap((r) => (r.status === "fulfilled" ? r.value : []));

  // Deduplicate by title (case-insensitive) against each other + existing
  const seen = new Set(existingFindings.map((f) => f.title.toLowerCase()));
  const unique = allRaw.filter((f) => {
    const key = f.title.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (unique.length > 0) {
    await prisma.finding.createMany({
      data: unique.map((f) => ({
        engagementId,
        title: f.title,
        severity: f.severity,
        category: f.category,
        description: f.description,
        recommendation: f.recommendation,
        aiGenerated: true,
      })),
    });
  }

  await prisma.engagement.update({
    where: { id: engagementId },
    data: { status: "ANALYSIS" },
  });

  const failed = settled.filter((r) => r.status === "rejected").length;
  if (failed > 0 && unique.length === 0) {
    return { error: `All ${failed} analysis types failed. Check active AI engine connectivity.` };
  }

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true, count: unique.length };
}
