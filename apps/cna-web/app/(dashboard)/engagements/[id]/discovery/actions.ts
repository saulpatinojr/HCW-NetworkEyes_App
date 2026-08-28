"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { decrypt } from "@/lib/crypto";
import { revalidatePath } from "next/cache";
import { checkRateLimit } from "@/lib/rate-limit";
import { dedupeDiscoveryFindings } from "@/lib/dedupe-findings";

export async function startAllDiscovery(
  engagementId: string,
): Promise<{ error?: string; started?: number }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  // OWA-02: Rate limit starting all discovery (5 requests per 60s)
  const isAllowed = await checkRateLimit(session.user.id, "startAllDiscovery");
  if (!isAllowed) {
    return { error: "Too many requests. Please wait before starting discovery again." };
  }

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const credentials = await prisma.cloudCredential.findMany({
    where: { engagementId },
  });
  if (!credentials.length) return { error: "No credentials configured." };

  // Clean up legacy duplicate findings at this mutation point (see helper).
  await dedupeDiscoveryFindings(engagementId);

  const apiUrl = process.env.CNA_API_INTERNAL_URL;
  if (!apiUrl) return { error: "Discovery API is not configured." };

  // Create all job records first in a single transaction so the UI
  // can display them immediately before any network I/O starts.
  const jobs = await prisma.$transaction(
    credentials.map((cred) =>
      prisma.discoveryJob.create({
        data: { engagementId, credentialId: cred.id, status: "QUEUED" },
      }),
    ),
  );

  // Fan out all API calls concurrently — previously sequential (for…of await)
  // which meant N credentials = N * round-trip latency before the action returned.
  const results = await Promise.allSettled(
    credentials.map(async (cred, i) => {
      const job = jobs[i];
      const spSecret = cred.spSecretEnc ? decrypt(cred.spSecretEnc) : null;
      const res = await fetch(`${apiUrl}/discovery/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: job.id,
          engagement_id: engagementId,
          credential_id: cred.id,
          tenant_id: cred.tenantId,
          subscription_ids: cred.subscriptionIds,
          sp_client_id: cred.spClientId,
          sp_client_secret: spSecret,
        }),
      });
      if (!res.ok) {
        await prisma.discoveryJob.update({
          where: { id: job.id },
          data: { status: "FAILED", errorMessage: `API error ${res.status}` },
        });
        throw new Error(`API error ${res.status}`);
      }
    }),
  );

  const started = results.filter((r) => r.status === "fulfilled").length;
  const failed = results.filter((r) => r.status === "rejected").length;
  if (failed > 0) {
    console.error(
      `startAllDiscovery: ${failed} job(s) failed for engagement ${engagementId}:`,
      results.filter((r) => r.status === "rejected").map((r) => (r as PromiseRejectedResult).reason),
    );
    await Promise.allSettled(
      results.map((r, i) => {
        if (r.status === "rejected") {
          return prisma.discoveryJob.update({
            where: { id: jobs[i].id },
            data: { status: "FAILED", errorMessage: String((r as PromiseRejectedResult).reason) },
          });
        }
      }),
    );
    if (started === 0)
      return {
        error: `All ${failed} discovery job(s) failed to start. Check the credential configuration and try again — details are in the job list below.`,
      };
  }

  revalidatePath(`/engagements/${engagementId}`);
  return { started };
}

export async function startDiscovery(
  _prev: { error?: string; jobId?: string } | null,
  formData: FormData,
): Promise<{ error?: string; jobId?: string }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  // OWA-02: Rate limit starting single discovery (5 requests per 60s)
  const isAllowed = await checkRateLimit(session.user.id, "startDiscovery");
  if (!isAllowed) {
    return { error: "Too many requests. Please wait before starting discovery again." };
  }

  const engagementId = formData.get("engagementId") as string | null;
  const credentialId = formData.get("credentialId") as string | null;
  if (!engagementId || !credentialId) return { error: "Missing parameters." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const cred = await prisma.cloudCredential.findUnique({
    where: { id: credentialId },
  });
  if (!cred || cred.engagementId !== engagementId) return { error: "Credential not found." };

  // Clean up legacy duplicate findings at this mutation point (see helper).
  await dedupeDiscoveryFindings(engagementId);

  const job = await prisma.discoveryJob.create({
    data: { engagementId, credentialId, status: "QUEUED" },
  });

  const apiUrl = process.env.CNA_API_INTERNAL_URL;
  if (!apiUrl) {
    await prisma.discoveryJob.update({
      where: { id: job.id },
      data: { status: "FAILED", errorMessage: "CNA_API_INTERNAL_URL is not configured." },
    });
    return { error: "Discovery API is not configured." };
  }

  const spSecret = cred.spSecretEnc ? decrypt(cred.spSecretEnc) : null;

  try {
    const res = await fetch(`${apiUrl}/discovery/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: job.id,
        engagement_id: engagementId,
        credential_id: cred.id,
        tenant_id: cred.tenantId,
        subscription_ids: cred.subscriptionIds,
        sp_client_id: cred.spClientId,
        sp_client_secret: spSecret,
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      await prisma.discoveryJob.update({
        where: { id: job.id },
        data: { status: "FAILED", errorMessage: `API error ${res.status}: ${body.slice(0, 300)}` },
      });
      return { error: "Failed to start discovery. Check API logs." };
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`Discovery start failed for job ${job.id}:`, err);
    await prisma.discoveryJob.update({
      where: { id: job.id },
      data: { status: "FAILED", errorMessage: message },
    });
    return { error: "Could not reach the discovery service. Please try again, or contact your administrator if it persists." };
  }

  revalidatePath(`/engagements/${engagementId}`);
  return { jobId: job.id };
}
