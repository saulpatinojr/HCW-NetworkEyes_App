"use server";

import { revalidatePath } from "next/cache";

import { auth } from "@/lib/auth";
import { getImageUpdateState } from "@/lib/image-update";

export async function checkImageUpdateAction(): Promise<void> {
  const session = await auth();
  if (!session?.user) {
    throw new Error("Authentication required.");
  }
  if (session.user.role !== "ADMIN") {
    throw new Error("Only admins can run an update check.");
  }
  await getImageUpdateState({ force: true });
  revalidatePath("/admin/updates");
}
