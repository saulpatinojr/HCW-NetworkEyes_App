"use server";

import { revalidatePath } from "next/cache";

import {
  ByoKeyRejectedError,
  clearByoApiKey,
  setByoApiKey,
} from "@/lib/ai-byo-credentials";
import { normalizeAiEngine, setActiveAiEngine } from "@/lib/ai-engine";
import { isByoProvider } from "@/lib/ai-engine-rules";
import { auth } from "@/lib/auth";

export type ByoKeyActionState = { error?: string; success?: string } | null;

async function requireAdmin(action: string) {
  const session = await auth();
  if (!session?.user) {
    throw new Error("Authentication required.");
  }
  if (session.user.role !== "ADMIN") {
    throw new Error(`Only admins can ${action}.`);
  }
  return session;
}

export async function setAiEngineAction(formData: FormData): Promise<void> {
  const session = await requireAdmin("switch the active AI engine");

  const engine = normalizeAiEngine(formData.get("engine")?.toString());
  if (!engine) {
    throw new Error("Invalid AI engine.");
  }

  await setActiveAiEngine(engine, session.user.id);
  revalidatePath("/admin/ai-engine");
}

export async function setByoApiKeyAction(
  _prev: ByoKeyActionState,
  formData: FormData,
): Promise<ByoKeyActionState> {
  const session = await requireAdmin("manage AI provider keys");

  const provider = formData.get("provider")?.toString() ?? "";
  if (!isByoProvider(provider)) return { error: "Invalid provider." };

  const apiKey = formData.get("apiKey")?.toString().trim() ?? "";
  if (!apiKey) return { error: "Paste an API key first." };

  try {
    await setByoApiKey(provider, apiKey, session.user.id);
  } catch (error) {
    if (error instanceof ByoKeyRejectedError) return { error: error.message };
    throw error;
  }

  revalidatePath("/admin/ai-engine");
  return { success: "Key saved and verified." };
}

export async function clearByoApiKeyAction(
  _prev: ByoKeyActionState,
  formData: FormData,
): Promise<ByoKeyActionState> {
  await requireAdmin("manage AI provider keys");

  const provider = formData.get("provider")?.toString() ?? "";
  if (!isByoProvider(provider)) return { error: "Invalid provider." };

  await clearByoApiKey(provider);
  revalidatePath("/admin/ai-engine");
  return { success: "Key removed." };
}
