"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { revalidatePath } from "next/cache";
import { generateDeliverableContent } from "@/lib/openai";

// ─── Multi-subscription topology merge (same pattern as deliverables/actions.ts) ─
async function getMergedTopologyJson(engagementId: string): Promise<string | null> {
  const completedJobs = await prisma.discoveryJob.findMany({
    where: { engagementId, status: "COMPLETED" },
    orderBy: { completedAt: "desc" },
    select: { topologyJson: true, credentialId: true },
    take: 100,
  }).catch(() => []);

  if (!completedJobs.length) return null;

  const latestByCredential = new Map<string, string>();
  for (const job of completedJobs) {
    const key = job.credentialId ?? "__none__";
    if (!latestByCredential.has(key) && job.topologyJson) {
      latestByCredential.set(key, job.topologyJson);
    }
  }

  if (latestByCredential.size === 0) return null;
  if (latestByCredential.size === 1) return [...latestByCredential.values()][0];

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

// ─── Create Interactive Assessment with AI-generated content ──────────────────

// Create a single INTERACTIVE_ASSESSMENT deliverable record (replaces existing).
// Calls the active AI engine to generate a fresh comprehensive HTML assessment every time.
export async function createInteractiveAssessment(
  engagementId: string,
): Promise<{ error?: string; success?: boolean }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

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
      where: { engagementId, type: { not: "INTERACTIVE_ASSESSMENT" } },
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
    return { error: "No findings yet. Run discovery and/or AI analysis before generating the interactive assessment." };
  }

  const mergedTopologyJson = await getMergedTopologyJson(engagementId);
  const date = new Date().toISOString().split("T")[0];
  const title = `${engagement.clientOrg} — Interactive Assessment — ${date}`;

  let content: string;
  try {
    content = await generateDeliverableContent({
      type: "COMPREHENSIVE_ASSESSMENT",
      title,
      clientOrg: engagement.clientOrg,
      engagementName: engagement.name,
      findings,
      topologyJson: mergedTopologyJson,
      documents: documents.map((d) => ({ fileName: d.fileName, text: d.parsedText! })),
      customerLogoUrl: null,
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
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("[generateInteractiveAssessment][error]", err);
    if (msg.includes("401") || msg.includes("PermissionDenied") || msg.includes("lacks the required")) {
      return { error: "AI generation failed: the web app is missing the required 'Cognitive Services User' access on the active AI resource." };
    }
    return { error: "AI generation failed. Check that the active AI engine is reachable, then try again — the full error has been logged." };
  }

  // Delete any previous interactive assessment and replace with the fresh AI-generated one
  await prisma.deliverable.deleteMany({
    where: { engagementId, type: "INTERACTIVE_ASSESSMENT" },
  });

  await prisma.deliverable.create({
    data: {
      engagementId,
      type: "INTERACTIVE_ASSESSMENT",
      title,
      content,
      publishedAt: new Date(),
      publishedBy: session.user.id,
    },
  });

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true };
}

// Delete a deliverable (any type) — canonical delete used from client-deliverables page
export async function deleteDeliverableFromPortal(formData: FormData) {
  const session = await auth();
  if (!session?.user?.id) return;

  const deliverableId = formData.get("deliverableId") as string | null;
  const engagementId = formData.get("engagementId") as string | null;
  if (!deliverableId || !engagementId) return;

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return;

  await prisma.deliverable.delete({ where: { id: deliverableId } });
  revalidatePath(`/engagements/${engagementId}`);
}

// Delete an uploaded document
export async function deleteDocument(formData: FormData) {
  const session = await auth();
  if (!session?.user?.id) return;

  const documentId = formData.get("documentId") as string | null;
  const engagementId = formData.get("engagementId") as string | null;
  if (!documentId || !engagementId) return;

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return;

  await prisma.ingestedDocument.delete({ where: { id: documentId } });
  revalidatePath(`/engagements/${engagementId}`);
}

// ─── Publish client portal ───────────────────────────────────────────────────
// Delegates to the CNA API, which uploads the published deliverables to a
// private per-engagement blob container and returns a TTL-capped SAS portal
// URL. The URL is returned to the caller ONCE and never persisted.

export async function publishClientPortal(
  engagementId: string,
  ttlHours: number = 168,
): Promise<{
  error?: string;
  portalUrl?: string;
  expiresAt?: string;
  deliverableCount?: number;
}> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const apiUrl = process.env.CNA_API_INTERNAL_URL;
  if (!apiUrl) return { error: "Discovery API is not configured." };

  try {
    const res = await fetch(`${apiUrl}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engagement_id: engagementId, ttl_hours: ttlHours }),
    });

    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { detail?: string } | null;
      return {
        error:
          body?.detail ??
          "Publishing the client portal failed. Please try again, or contact your administrator if it persists.",
      };
    }

    const data = (await res.json()) as {
      portal_url: string;
      expires_at: string;
      deliverable_count: number;
    };

    revalidatePath(`/engagements/${engagementId}/client-deliverables`);
    return {
      portalUrl: data.portal_url,
      expiresAt: data.expires_at,
      deliverableCount: data.deliverable_count,
    };
  } catch (err: unknown) {
    console.error("[publishClientPortal] error:", err);
    return {
      error:
        "Could not reach the publishing service. Please try again, or contact your administrator if it persists.",
    };
  }
}
