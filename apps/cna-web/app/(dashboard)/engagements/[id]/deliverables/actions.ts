"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { deleteBlob, uploadDeliverable } from "@/lib/blob";
import { generateDeliverableContent } from "@/lib/openai";
import type { DeliverableContext, DeliverableType as OpenAIDeliverableType } from "@/lib/openai";
import { generateComprehensiveReport, type ProgressUpdate } from "@/lib/report-orchestrator";
import { revalidatePath } from "next/cache";
import { after } from "next/server";
import type { DeliverableType } from "@prisma/client";
import { checkRateLimit } from "@/lib/rate-limit";

// ─── Multi-subscription topology merge ────────────────────────────────────────
// Each CloudCredential is one subscription sync group. We take the latest
// completed job per credential and merge all their topologies into one JSON
// so the assessment covers every scanned subscription, not just the most
// recently synced one.

async function getMergedTopologyJson(engagementId: string): Promise<string | null> {
  const completedJobs = await prisma.discoveryJob.findMany({
    where: { engagementId, status: "COMPLETED" },
    orderBy: { completedAt: "desc" },
    select: { topologyJson: true, credentialId: true },
    take: 100,
  }).catch(() => []);

  if (!completedJobs.length) return null;

  // Latest job per credential
  const latestByCredential = new Map<string, string>();
  for (const job of completedJobs) {
    const key = job.credentialId ?? "__none__";
    if (!latestByCredential.has(key) && job.topologyJson) {
      latestByCredential.set(key, job.topologyJson);
    }
  }

  if (latestByCredential.size === 0) return null;
  if (latestByCredential.size === 1) return [...latestByCredential.values()][0];

  // Merge: deduplicate subscriptions by subscription_id
  let tenantId = "";
  const seenSubIds = new Set<string>();
  const mergedSubs: unknown[] = [];

  for (const json of latestByCredential.values()) {
    try {
      const topo = JSON.parse(json) as { tenant_id?: string; subscriptions?: Array<{ subscription_id?: string }> };
      if (!tenantId && topo.tenant_id) tenantId = topo.tenant_id;
      for (const sub of topo.subscriptions ?? []) {
        if (sub.subscription_id && !seenSubIds.has(sub.subscription_id)) {
          seenSubIds.add(sub.subscription_id);
          mergedSubs.push(sub);
        }
      }
    } catch { /* skip malformed */ }
  }

  return JSON.stringify({ tenant_id: tenantId, subscriptions: mergedSubs });
}

const TYPE_LABELS: Record<string, string> = {
  COMPREHENSIVE_ASSESSMENT: "Comprehensive Assessment",
  EXECUTIVE_SUMMARY: "Executive Summary",
  TECHNICAL_FINDINGS: "Technical Findings",
  REMEDIATION_PLAN: "Remediation Plan",
  SPECIALIZATION_REPORT: "Specialization Report",
  ENCYCLOPEDIA_CONDENSED: "Networking Encyclopedia (Condensed)",
  ENCYCLOPEDIA_EXPANDED: "Networking Encyclopedia (Expanded)",
};

// Encyclopedia editions are rendered by the Python report engine via cna-api
// (not the OpenAI deliverable prompts).
const ENCYCLOPEDIA_EDITIONS: Record<string, "condensed" | "expanded"> = {
  ENCYCLOPEDIA_CONDENSED: "condensed",
  ENCYCLOPEDIA_EXPANDED: "expanded",
};

// COMPREHENSIVE_ASSESSMENT is dispatched to the background orchestrator, not
// generated inline with these single-shot types.
const SINGLE_SHOT_TYPES: OpenAIDeliverableType[] = [
  "EXECUTIVE_SUMMARY",
  "TECHNICAL_FINDINGS",
  "REMEDIATION_PLAN",
  "SPECIALIZATION_REPORT",
];

function buildTitle(type: string, clientOrg: string, seqNum: number): string {
  const label = TYPE_LABELS[type] ?? type.replace(/_/g, " ");
  const date = new Date().toISOString().split("T")[0];
  return `${clientOrg} — ${label} — ${date} — #${seqNum}`;
}

// ─── Background generation for the sectioned Comprehensive Assessment ────────
// Multi-pass generation (12+ AI calls) exceeds the Front Door / Container Apps
// ingress timeouts, so the orchestrator runs via next/server after() and the
// client polls getDeliverableProgress(). Progress steps accumulate in
// Deliverable.progressLog as a JSON array.

async function runComprehensiveInBackground(
  deliverableId: string,
  engagementId: string,
  ctx: DeliverableContext,
): Promise<void> {
  const steps: ProgressUpdate[] = [];
  const persistProgress = async (update: ProgressUpdate) => {
    const existing = steps.findIndex((s) => s.stepId === update.stepId);
    if (existing >= 0) steps[existing] = update;
    else steps.push(update);
    await prisma.deliverable
      .update({
        where: { id: deliverableId },
        data: { progressLog: JSON.stringify(steps) },
      })
      .catch(() => {}); // progress persistence must never kill the run
  };

  try {
    const content = await generateComprehensiveReport(ctx, persistProgress);
    const fileName = `comprehensive_assessment-${Date.now()}.md`;
    const blobPath = await uploadDeliverable(engagementId, fileName, content);
    await prisma.deliverable.update({
      where: { id: deliverableId },
      data: { content, blobPath, status: "COMPLETED", progressLog: JSON.stringify(steps) },
    });
    await prisma.engagement.update({
      where: { id: engagementId },
      data: { status: "REVIEW" },
    });
  } catch (err) {
    console.error("[runComprehensiveInBackground][error]", err);
    await prisma.deliverable
      .update({
        where: { id: deliverableId },
        data: {
          status: "FAILED",
          progressLog: JSON.stringify([...steps, { stepId: "fatal", label: "Generation failed — the error has been logged. Retry, or contact your administrator if it persists.", status: "failed" }]),
        },
      })
      .catch(() => {});
  }
}

/** Poll target for the deliverables page while a report is QUEUED/RUNNING. */
export async function getDeliverableProgress(
  deliverableId: string,
): Promise<{ status: string; steps: ProgressUpdate[] } | null> {
  const session = await auth();
  if (!session?.user?.id) return null;

  const deliverable = await prisma.deliverable.findUnique({
    where: { id: deliverableId },
    select: {
      status: true,
      progressLog: true,
      engagement: { select: { members: { select: { userId: true } } } },
    },
  });
  if (!deliverable) return null;
  if (!deliverable.engagement.members.some((m) => m.userId === session.user!.id)) return null;

  let steps: ProgressUpdate[] = [];
  try {
    steps = deliverable.progressLog ? (JSON.parse(deliverable.progressLog) as ProgressUpdate[]) : [];
  } catch { /* malformed progress — return empty */ }
  return { status: deliverable.status, steps };
}

// OWA-07: SSRF Defense - Validate that external image URLs are restricted to trusted domains
function validateLogoUrl(url: string | null): { error?: string } | null {
  if (!url || url.trim() === "") return null;
  try {
    if (!url.startsWith("/")) {
      const parsed = new URL(url);
      const allowedLogoHosts = ["cdn.cbts.com", "storage.azure.com", "githubusercontent.com", "cbts.com"];
      const isAllowed = allowedLogoHosts.some(
        (host) => parsed.hostname === host || parsed.hostname.endsWith("." + host)
      );
      if (!isAllowed) {
        return { error: "Logo URL must be hosted on an approved CDN (e.g., *.cbts.com)." };
      }
    }
    return null;
  } catch {
    return { error: "Invalid customer logo URL format." };
  }
}

// ─── Generate single assessment ───────────────────────────────────────────────

export async function generateDeliverable(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  // OWA-02: Rate limit deliverable generation (5 requests per 60s)
  const isAllowed = await checkRateLimit(session.user.id, "generateDeliverable");
  if (!isAllowed) {
    return { error: "Too many requests. Please wait before generating deliverables again." };
  }

  const engagementId = formData.get("engagementId") as string | null;
  const type = formData.get("type") as string | null;
  const customerLogoUrl = (formData.get("customerLogoUrl") as string | null) ?? null;
  const validationError = validateLogoUrl(customerLogoUrl);
  if (validationError) return validationError;

  if (!engagementId || !type) return { error: "Missing required fields." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const [engagement, findings, documents, existingDeliverables, credentials] = await Promise.all([
    prisma.engagement.findUnique({ where: { id: engagementId } }),
    prisma.finding.findMany({
      where: { engagementId },
      orderBy: [{ severity: "asc" }, { createdAt: "asc" }],
    }),
    prisma.ingestedDocument.findMany({
      where: { engagementId, parsedText: { not: null } },
      select: { fileName: true, parsedText: true },
    }),
    prisma.deliverable.findMany({
      where: { engagementId },
      orderBy: { createdAt: "desc" },
      select: { type: true, title: true },
    }),
    prisma.cloudCredential.findMany({
      where: { engagementId },
      select: { label: true, platform: true, tenantId: true, subscriptionIds: true },
    }),
  ]);

  if (!engagement) return { error: "Engagement not found." };
  if (findings.length === 0) {
    return { error: "No findings yet. Run discovery and/or AI analysis before generating assessments." };
  }

  // Merged topology from ALL subscription sync groups
  const mergedTopologyJson = await getMergedTopologyJson(engagementId);

  const title = buildTitle(type, engagement.clientOrg, existingDeliverables.length + 1);

  let content: string;
  if (type in ENCYCLOPEDIA_EDITIONS) {
    const apiUrl = process.env.CNA_API_INTERNAL_URL;
    if (!apiUrl) return { error: "Report API is not configured (CNA_API_INTERNAL_URL unset)." };
    try {
      const res = await fetch(`${apiUrl}/reports/${engagementId}/encyclopedia`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          edition: ENCYCLOPEDIA_EDITIONS[type],
          client_org: engagement.clientOrg,
          engagement_name: engagement.name,
          generated_at: new Date().toISOString(),
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(90_000),
      });
      if (!res.ok) {
        const body = await res.text();
        console.error("[generateDeliverable][encyclopedia]", res.status, body.slice(0, 500));
        return { error: `Encyclopedia generation failed (API error ${res.status}).` };
      }
      const json = (await res.json().catch(() => null)) as { content?: unknown } | null;
      if (!json || typeof json.content !== "string") {
        return { error: "Encyclopedia generation failed (invalid API response)." };
      }
      content = json.content
    } catch (err) {
      console.error("[generateDeliverable][encyclopedia][error]", err);
      return { error: "Could not reach the report service. Please try again, or contact your administrator if it persists." };
    }

    const fileName = `${type.toLowerCase()}-${Date.now()}.html`;
    const blobPath = await uploadDeliverable(engagementId, fileName, content);
    await prisma.deliverable.create({
      data: { engagementId, title, type: type as DeliverableType, blobPath, content },
    });
    await prisma.engagement.update({
      where: { id: engagementId },
      data: { status: "REVIEW" },
    });
    revalidatePath(`/engagements/${engagementId}`);
    return { success: true };
  }
  const deliverableCtx: DeliverableContext = {
    type: type as OpenAIDeliverableType,
    title,
    clientOrg: engagement.clientOrg,
    engagementName: engagement.name,
    findings,
    topologyJson: mergedTopologyJson,
    documents: documents.map((d) => ({ fileName: d.fileName, text: d.parsedText! })),
    customerLogoUrl,
    credentialsInfo: credentials.map((c) => ({
      label: c.label,
      platform: c.platform,
      tenantId: c.tenantId,
      subscriptionIds: c.subscriptionIds,
    })),
    previousAssessments: existingDeliverables.map((d) => ({
      type: d.type,
      title: d.title,
    })),
  };

  // Sectioned Comprehensive Assessment: 12+ AI calls exceed edge timeouts, so
  // create the row immediately (RUNNING) and generate in the background.
  if (type === "COMPREHENSIVE_ASSESSMENT") {
    const row = await prisma.deliverable.create({
      data: {
        engagementId,
        title,
        type: type as DeliverableType,
        status: "RUNNING",
        progressLog: "[]",
      },
    });
    after(() => runComprehensiveInBackground(row.id, engagementId, deliverableCtx));
    revalidatePath(`/engagements/${engagementId}`);
    return { success: true };
  }

  try {
    content = await generateDeliverableContent(deliverableCtx);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("[generateDeliverable][error]", err);
    if (msg.includes("401") || msg.includes("PermissionDenied") || msg.includes("lacks the required")) {
      return { error: "AI generation failed: the web app is missing the required 'Cognitive Services User' access on the active AI resource." };
    }
    return { error: "AI generation failed. Please check the server logs for details." };
  }

  const fileName = `${type.toLowerCase()}-${Date.now()}.md`;
  const blobPath = await uploadDeliverable(engagementId, fileName, content);

  await prisma.deliverable.create({
    data: { engagementId, title, type: type as DeliverableType, blobPath, content },
  });

  await prisma.engagement.update({
    where: { id: engagementId },
    data: { status: "REVIEW" },
  });

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true };
}

// ─── Generate all assessment types ────────────────────────────────────────────

export async function generateAllAssessments(
  _prev: { error?: string; success?: boolean; count?: number } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean; count?: number }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  // OWA-02: Rate limit generating all assessments (5 requests per 60s)
  const isAllowed = await checkRateLimit(session.user.id, "generateAllAssessments");
  if (!isAllowed) {
    return { error: "Too many requests. Please wait before generating deliverables again." };
  }

  const engagementId = formData.get("engagementId") as string | null;
  const customerLogoUrl = (formData.get("customerLogoUrl") as string | null) ?? null;
  const validationError = validateLogoUrl(customerLogoUrl);
  if (validationError) return validationError;

  if (!engagementId) return { error: "Missing engagement ID." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const [engagement, findings, documents, existingDeliverables, credentials] = await Promise.all([
    prisma.engagement.findUnique({ where: { id: engagementId } }),
    prisma.finding.findMany({
      where: { engagementId },
      orderBy: [{ severity: "asc" }, { createdAt: "asc" }],
    }),
    prisma.ingestedDocument.findMany({
      where: { engagementId, parsedText: { not: null } },
      select: { fileName: true, parsedText: true },
    }),
    prisma.deliverable.findMany({
      where: { engagementId },
      orderBy: { createdAt: "desc" },
      select: { type: true, title: true },
    }),
    prisma.cloudCredential.findMany({
      where: { engagementId },
      select: { label: true, platform: true, tenantId: true, subscriptionIds: true },
    }),
  ]);

  if (!engagement) return { error: "Engagement not found." };
  if (findings.length === 0) {
    return { error: "No findings yet. Run discovery and/or AI analysis before generating assessments." };
  }

  const docInput = documents.map((d) => ({ fileName: d.fileName, text: d.parsedText! }));
  const mergedTopologyJson = await getMergedTopologyJson(engagementId);
  const credentialsInfo = credentials.map((c) => ({
    label: c.label,
    platform: c.platform,
    tenantId: c.tenantId,
    subscriptionIds: c.subscriptionIds,
  }));
  const previousAssessments = existingDeliverables.map((d) => ({ type: d.type, title: d.title }));

  // Dispatch the sectioned Comprehensive Assessment to the background first.
  const comprehensiveTitle = buildTitle(
    "COMPREHENSIVE_ASSESSMENT",
    engagement.clientOrg,
    existingDeliverables.length + 1,
  );
  const comprehensiveRow = await prisma.deliverable.create({
    data: {
      engagementId,
      title: comprehensiveTitle,
      type: "COMPREHENSIVE_ASSESSMENT",
      status: "RUNNING",
      progressLog: "[]",
    },
  });
  after(() =>
    runComprehensiveInBackground(comprehensiveRow.id, engagementId, {
      type: "COMPREHENSIVE_ASSESSMENT",
      title: comprehensiveTitle,
      clientOrg: engagement.clientOrg,
      engagementName: engagement.name,
      findings,
      topologyJson: mergedTopologyJson,
      documents: docInput,
      customerLogoUrl,
      credentialsInfo,
      previousAssessments,
    }),
  );

  const settled = await Promise.allSettled(
    SINGLE_SHOT_TYPES.map((type, i) =>
      generateDeliverableContent({
        type,
        title: buildTitle(type, engagement.clientOrg, existingDeliverables.length + i + 2),
        clientOrg: engagement.clientOrg,
        engagementName: engagement.name,
        findings,
        topologyJson: mergedTopologyJson,
        documents: docInput,
        customerLogoUrl,
        credentialsInfo,
        previousAssessments,
      }).then((content) => ({ type, content })),
    ),
  );

  let saved = 1; // the background comprehensive row counts as dispatched
  for (const result of settled) {
    if (result.status !== "fulfilled") continue;
    const { type, content } = result.value;
    const fileName = `${type.toLowerCase()}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}.md`;
    try {
      const blobPath = await uploadDeliverable(engagementId, fileName, content);
      const title = buildTitle(type, engagement.clientOrg, existingDeliverables.length + saved + 1);
      await prisma.deliverable.create({
        data: { engagementId, title, type, blobPath, content },
      });
      saved++;
    } catch { /* skip failed saves */ }
  }

  const failed = settled.filter((r) => r.status === "rejected").length;
  if (failed > 0 && saved <= 1) {
    return { error: `All ${failed} synchronous assessment generations failed. Check active AI engine connectivity. (The Comprehensive Assessment was dispatched in the background — check its status on the deliverables list.)` };
  }

  await prisma.engagement.update({
    where: { id: engagementId },
    data: { status: "REVIEW" },
  });

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true, count: saved };
}

// ─── Delete assessment ─────────────────────────────────────────────────────────

export async function deleteDeliverable(formData: FormData) {
  const session = await auth();
  if (!session?.user?.id) return;

  const deliverableId = formData.get("deliverableId") as string | null;
  const engagementId = formData.get("engagementId") as string | null;
  if (!deliverableId || !engagementId) return;

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return;

  const record = await prisma.deliverable.findUnique({
    where: { id: deliverableId },
    select: { blobPath: true },
  });
  if (record?.blobPath) {
    await deleteBlob(record.blobPath);
  }

  await prisma.deliverable.delete({ where: { id: deliverableId } });
  revalidatePath(`/engagements/${engagementId}`);
}

export async function cleanupExpiredDeliverables(engagementId: string): Promise<number> {
  const cutoff = new Date(Date.now() - 90 * 24 * 3600 * 1000);
  const expired = await prisma.deliverable.findMany({
    where: { engagementId, createdAt: { lt: cutoff } },
  });
  let deleted = 0;
  for (const d of expired) {
    if (d.blobPath) {
      await deleteBlob(d.blobPath);
    }
    await prisma.deliverable.delete({ where: { id: d.id } });
    deleted++;
  }
  return deleted;
}

// ─── Publish assessment ────────────────────────────────────────────────────────

export async function publishDeliverable(formData: FormData) {
  const session = await auth();
  if (!session?.user?.id) return;

  const deliverableId = formData.get("deliverableId") as string | null;
  const engagementId = formData.get("engagementId") as string | null;
  if (!deliverableId || !engagementId) return;

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return;

  await prisma.deliverable.update({
    where: { id: deliverableId },
    data: { publishedAt: new Date(), publishedBy: session.user.id },
  });

  await prisma.engagement.update({
    where: { id: engagementId },
    data: { status: "DELIVERED" },
  });

  revalidatePath(`/engagements/${engagementId}`);
}
