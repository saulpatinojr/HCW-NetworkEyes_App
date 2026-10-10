"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { encrypt } from "@/lib/crypto";
import { sanitizeBackendDetail } from "@/lib/summarize-error";
import { apiHeaders } from "@/lib/api-client";
import { revalidatePath } from "next/cache";

// ─── Add credential ───────────────────────────────────────────────────────────

export async function addCloudCredential(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const engagementId = formData.get("engagementId") as string | null;
  const label = (formData.get("label") as string | null)?.trim() ?? "";
  const tenantId = (formData.get("tenantId") as string | null)?.trim() ?? "";
  const subscriptionIdsRaw = (formData.get("subscriptionIds") as string | null)?.trim() ?? "";
  const spClientId = (formData.get("spClientId") as string | null)?.trim() ?? "";
  const spClientSecret = (formData.get("spClientSecret") as string | null)?.trim() ?? "";

  if (!engagementId || !label || !tenantId) {
    return { error: "Label and Tenant ID are required." };
  }
  if (!spClientId || !spClientSecret) {
    return { error: "Service Principal Client ID and Secret are required." };
  }

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const subscriptionIds = subscriptionIdsRaw
    ? subscriptionIdsRaw.split(",").map((s) => s.trim()).filter(Boolean)
    : [];

  const spSecretEnc = encrypt(spClientSecret);

  await prisma.cloudCredential.upsert({
    where: { engagementId_label: { engagementId, label } },
    create: {
      engagementId,
      platform: "AZURE",
      label,
      tenantId,
      subscriptionIds,
      spClientId,
      spSecretEnc,
    },
    update: {
      tenantId,
      subscriptionIds,
      spClientId,
      spSecretEnc,
    },
  });

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true };
}

// ─── Bulk-add credentials (one per subscription) ─────────────────────────────

export async function addBulkCredentials(params: {
  engagementId: string;
  tenantId: string;
  spClientId: string;
  spClientSecret: string;
  subscriptions: { name: string; subscriptionId: string; tenantId?: string }[];
}): Promise<{ error?: string; success?: boolean; count?: number }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const { engagementId, tenantId, spClientId, spClientSecret, subscriptions } = params;

  if (!engagementId || !tenantId || !spClientId || !spClientSecret) {
    return { error: "Tenant ID, Client ID, and Client Secret are all required." };
  }
  if (!subscriptions.length) {
    return { error: "Add at least one subscription." };
  }

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const spSecretEnc = encrypt(spClientSecret);

  // Deduplicate by label before saving (last row with same name wins).
  const byLabel = new Map<string, (typeof subscriptions)[0]>();
  for (const sub of subscriptions) byLabel.set(sub.name, sub);
  const unique = Array.from(byLabel.values());

  await prisma.$transaction(
    unique.map((sub) => {
      const effectiveTenantId = (sub.tenantId?.trim() || tenantId).trim();
      return prisma.cloudCredential.upsert({
        where: { engagementId_label: { engagementId, label: sub.name } },
        create: {
          engagementId,
          platform: "AZURE",
          label: sub.name,
          tenantId: effectiveTenantId,
          subscriptionIds: [sub.subscriptionId],
          spClientId,
          spSecretEnc,
        },
        update: {
          tenantId: effectiveTenantId,
          subscriptionIds: [sub.subscriptionId],
          spClientId,
          spSecretEnc,
        },
      });
    }),
  );

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true, count: unique.length };
}

// ─── Delete credential ────────────────────────────────────────────────────────

export async function deleteCloudCredential(
  _prev: { error?: string; deleted?: boolean } | null,
  formData: FormData,
): Promise<{ error?: string; deleted?: boolean }> {
  try {
    const session = await auth();
    if (!session?.user?.id) return { error: "Not authenticated." };

    const credentialId = formData.get("credentialId") as string | null;
    const engagementId = formData.get("engagementId") as string | null;
    if (!credentialId || !engagementId) return { error: "Missing parameters." };

    const member = await prisma.engagementMember.findUnique({
      where: { engagementId_userId: { engagementId, userId: session.user.id } },
    });
    if (!member) return { error: "Access denied." };

    // SEC-002 / C5: authorise on the *target row's* engagement, not the
    // caller-supplied engagementId alone. Confirm the credential actually
    // belongs to the engagement the caller is a member of before mutating it,
    // and scope every downstream delete/update by that engagementId too.
    const cred = await prisma.cloudCredential.findFirst({
      where: { id: credentialId, engagementId },
      select: { id: true },
    });
    if (!cred) return { error: "Credential not found." };

    // Delete all discovery findings tied to this subscription before removing the credential
    await prisma.finding.deleteMany({ where: { credentialId, engagementId, aiGenerated: false } });

    // Null out credentialId on any discovery jobs referencing this credential
    // before deleting to satisfy the FK constraint on older DB migrations.
    await prisma.discoveryJob.updateMany({
      where: { credentialId, engagementId },
      data: { credentialId: null },
    });
    await prisma.cloudCredential.deleteMany({ where: { id: credentialId, engagementId } });

    return { deleted: true };
  } catch {
    return { error: "Failed to delete credential. Please try again." };
  }
}

// ─── Test Azure connection ────────────────────────────────────────────────────
// Called directly from a client component (not via form submission).

export async function testAzureConnection(params: {
  tenantId: string;
  spClientId: string;
  spClientSecret: string;
}): Promise<{ ok: boolean; subscriptions?: string[]; error?: string }> {
  const session = await auth();
  if (!session?.user?.id) return { ok: false, error: "Not authenticated." };

  const { tenantId, spClientId, spClientSecret } = params;
  if (!tenantId || !spClientId || !spClientSecret) {
    return { ok: false, error: "Tenant ID, Client ID, and Client Secret are all required." };
  }

  try {
    const { ClientSecretCredential } = await import("@azure/identity");
    const credential = new ClientSecretCredential(tenantId, spClientId, spClientSecret);
    const tokenResponse = await credential.getToken(
      "https://management.azure.com/.default",
    );

    const res = await fetch(
      "https://management.azure.com/subscriptions?api-version=2022-12-01",
      { headers: { Authorization: `Bearer ${tokenResponse.token}` } },
    );

    if (!res.ok) {
      const body = await res.text();
      console.error(`[testConnection] ARM API ${res.status}:`, body.slice(0, 500));
      return {
        ok: false,
        error:
          res.status === 401 || res.status === 403
            ? "Azure rejected the credentials. Verify the Tenant ID, SP Client ID, and SP Client Secret, and that the service principal has been granted access."
            : `Azure did not accept the request (HTTP ${res.status}). Please try again, or contact your administrator if it persists.`,
      };
    }

    const data = (await res.json()) as {
      value?: { subscriptionId: string; displayName: string }[];
    };
    const subscriptions = (data.value ?? []).map(
      (s) => `${s.displayName} (${s.subscriptionId})`,
    );

    return { ok: true, subscriptions };
  } catch (err: unknown) {
    console.error("[testConnection] error:", err);
    return {
      ok: false,
      error:
        "Could not validate the credentials against Azure. Verify the Tenant ID, SP Client ID, and SP Client Secret, then try again.",
    };
  }
}

// ─── Add AWS credential ──────────────────────────────────────────────────────

export async function addAwsCredential(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const engagementId = formData.get("engagementId") as string | null;
  const label = (formData.get("label") as string | null)?.trim() ?? "";
  const awsRoleArn = (formData.get("awsRoleArn") as string | null)?.trim() ?? "";
  const awsExternalId = (formData.get("awsExternalId") as string | null)?.trim() ?? "";
  const awsRegionsRaw = (formData.get("awsRegions") as string | null)?.trim() ?? "";
  const awsAccessKeyId = (formData.get("awsAccessKeyId") as string | null)?.trim() ?? "";
  const awsSecretAccessKey = (formData.get("awsSecretAccessKey") as string | null)?.trim() ?? "";

  if (!engagementId || !label || !awsRoleArn) {
    return { error: "Label and read-only Role ARN are required." };
  }
  if (!/^arn:aws[a-z-]*:iam::\d{12}:role\/.+$/.test(awsRoleArn)) {
    return { error: "Role ARN must look like arn:aws:iam::123456789012:role/CNA-ReadOnly." };
  }
  if (!awsAccessKeyId || !awsSecretAccessKey) {
    return { error: "Access Key ID and Secret Access Key are required." };
  }

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const awsRegions = awsRegionsRaw
    ? awsRegionsRaw.split(",").map((s) => s.trim()).filter(Boolean)
    : [];

  const awsSecretEnc = encrypt(awsSecretAccessKey);

  await prisma.cloudCredential.upsert({
    where: { engagementId_label: { engagementId, label } },
    create: {
      engagementId,
      platform: "AWS",
      label,
      awsRoleArn,
      awsExternalId: awsExternalId || null,
      awsRegions,
      awsAccessKeyId,
      awsSecretEnc,
    },
    update: {
      awsRoleArn,
      awsExternalId: awsExternalId || null,
      awsRegions,
      awsAccessKeyId,
      awsSecretEnc,
    },
  });

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true };
}

// ─── Test AWS connection ─────────────────────────────────────────────────────
// Validated by the CNA API (which has boto3) rather than in the web layer.

export async function testAwsConnection(params: {
  roleArn: string;
  externalId?: string;
  accessKeyId: string;
  secretAccessKey: string;
}): Promise<{ ok: boolean; callerAccount?: string; assumedRoleArn?: string; error?: string }> {
  const session = await auth();
  if (!session?.user?.id) return { ok: false, error: "Not authenticated." };

  const { roleArn, externalId, accessKeyId, secretAccessKey } = params;
  if (!roleArn || !accessKeyId || !secretAccessKey) {
    return { ok: false, error: "Role ARN, Access Key ID, and Secret Access Key are all required." };
  }

  const apiUrl = process.env.CNA_API_INTERNAL_URL;
  if (!apiUrl) return { ok: false, error: "Discovery API is not configured." };

  try {
    const res = await fetch(`${apiUrl}/discovery/test-connection-aws`, {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        role_arn: roleArn,
        external_id: externalId || null,
        access_key_id: accessKeyId,
        secret_access_key: secretAccessKey,
      }),
    });

    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { detail?: string } | null;
      return {
        ok: false,
        error: sanitizeBackendDetail(
          body?.detail,
          "AWS rejected the credentials. Verify the access key, secret, role ARN, and external ID.",
        ),
      };
    }

    const data = (await res.json()) as { caller_account?: string; assumed_role_arn?: string };
    return { ok: true, callerAccount: data.caller_account, assumedRoleArn: data.assumed_role_arn };
  } catch (err: unknown) {
    console.error("[testAwsConnection] error:", err);
    return {
      ok: false,
      error: "Could not reach the discovery service to validate the AWS credentials. Please try again.",
    };
  }
}
