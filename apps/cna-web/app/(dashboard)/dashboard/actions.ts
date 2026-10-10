"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { deleteBlob, deleteContainer } from "@/lib/blob";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

export async function createEngagement(formData: FormData) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/signin");
  }

  const name = (formData.get("name") as string | null)?.trim() ?? "";
  const clientOrg = (formData.get("clientOrg") as string | null)?.trim() ?? "";

  if (!name || !clientOrg) {
    throw new Error("Engagement name and client organization are required.");
  }

  const engagement = await prisma.engagement.create({
    data: {
      name,
      clientOrg,
      members: {
        create: {
          userId: session.user.id,
          role: "ADMIN",
        },
      },
    },
  });

  revalidatePath("/dashboard");
  redirect(`/engagements/${engagement.id}`);
}

export async function deleteEngagement(formData: FormData) {
  const session = await auth();
  if (!session?.user?.id) {
    redirect("/auth/signin");
  }

  const engagementId = (formData.get("engagementId") as string | null)?.trim();
  if (!engagementId) return;

  // SEC-007 / C5: deleting a whole engagement (and every credential, finding,
  // deliverable and document in it) is destructive — restrict it to an
  // engagement ADMIN or a platform ADMIN. The engagement creator is granted an
  // ADMIN membership at creation time (see createEngagement), so this also
  // covers the owner without a dedicated createdById column. A plain member
  // (ANALYST / REVIEWER / CLIENT) cannot delete the engagement.
  const member = await prisma.engagementMember.findUnique({
    where: {
      engagementId_userId: { engagementId, userId: session.user.id },
    },
  });
  const isPlatformAdmin = session.user.role === "ADMIN";
  if (!member && !isPlatformAdmin) return;
  if (member && member.role !== "ADMIN" && !isPlatformAdmin) return;

  // DATA-001 / C6: remove backing object storage before the DB row so customer
  // artifacts are not orphaned. Best-effort — log and continue on blob errors,
  // then delete the row regardless (an orphaned blob is preferable to a
  // half-deleted engagement).
  const [documents, deliverables] = await Promise.all([
    prisma.ingestedDocument.findMany({
      where: { engagementId },
      select: { blobPath: true },
    }),
    prisma.deliverable.findMany({
      where: { engagementId, blobPath: { not: null } },
      select: { blobPath: true },
    }),
  ]);

  const blobPaths = [
    ...documents.map((d) => d.blobPath),
    ...deliverables.map((d) => d.blobPath),
  ].filter((p): p is string => Boolean(p));

  for (const blobPath of blobPaths) {
    try {
      await deleteBlob(blobPath);
    } catch (err) {
      console.error(`[deleteEngagement] blob delete failed for ${blobPath} (orphaned):`, err);
    }
  }

  // The per-engagement client-portal container (see cna-api /publish).
  try {
    await deleteContainer(`portal-${engagementId}`);
  } catch (err) {
    console.error(`[deleteEngagement] portal container delete failed for portal-${engagementId} (orphaned):`, err);
  }

  await prisma.engagement.delete({ where: { id: engagementId } });

  revalidatePath("/dashboard");
  redirect("/dashboard");
}
