import Anthropic from "@anthropic-ai/sdk";
import OpenAI from "openai";

import { decrypt, encrypt } from "@/lib/crypto";
import { prisma } from "@/lib/prisma";

import { BYO_ENGINES, clean, type ByoProvider } from "./ai-engine-rules";

/**
 * Bring-your-own AI provider keys — the only secrets an admin enters in the
 * app UI. Stored as AppSetting rows (global singletons, like ai.activeEngine),
 * AES-256-GCM encrypted with the same lib/crypto.ts helper the cloud
 * credentials use. cna-api reads the same rows and decrypts them with
 * cna/core/credential_crypto.py — keep the key names in sync with
 * apps/cna-api/routers/chat.py.
 *
 *   ai.byo.<provider>.apiKey   encrypted blob
 *   ai.byo.<provider>.keyHint  last four characters, for the admin page
 *   ai.byo.<provider>.model    optional model override
 *
 * Decrypted keys never leave the server and are never returned to the client.
 */

type ByoField = "apiKey" | "keyHint" | "model";

export function byoSettingKey(provider: ByoProvider, field: ByoField): string {
  return `ai.byo.${provider}.${field}`;
}

export type ByoCredentialStatus = {
  configured: boolean;
  hint: string | null;
  model: string | null;
};

export type ByoCredentialPresence = Record<ByoProvider, ByoCredentialStatus>;

export const PROVIDER_LABELS: Readonly<Record<ByoProvider, string>> = {
  anthropic: "Anthropic Claude",
  openai: "OpenAI",
};

const ALL_BYO_KEYS = BYO_ENGINES.flatMap((provider) =>
  (["apiKey", "keyHint", "model"] as const).map((field) => byoSettingKey(provider, field)),
);

export function emptyByoPresence(): ByoCredentialPresence {
  return {
    anthropic: { configured: false, hint: null, model: null },
    openai: { configured: false, hint: null, model: null },
  };
}

/** Presence + hint only — never decrypts. Safe to feed to the admin page. */
export async function getByoCredentialPresence(): Promise<ByoCredentialPresence> {
  const rows = await prisma.appSetting.findMany({
    where: { key: { in: ALL_BYO_KEYS } },
    select: { key: true, value: true },
  });
  const byKey = new Map(rows.map((row) => [row.key, row.value]));

  const presence = emptyByoPresence();
  for (const provider of BYO_ENGINES) {
    presence[provider] = {
      configured: Boolean(clean(byKey.get(byoSettingKey(provider, "apiKey")))),
      hint: clean(byKey.get(byoSettingKey(provider, "keyHint"))) || null,
      model: clean(byKey.get(byoSettingKey(provider, "model"))) || null,
    };
  }
  return presence;
}

/** Server-only: the plaintext key for a transport call. */
export async function getDecryptedByoApiKey(provider: ByoProvider): Promise<string | null> {
  const row = await prisma.appSetting.findUnique({
    where: { key: byoSettingKey(provider, "apiKey") },
    select: { value: true },
  });
  const blob = clean(row?.value);
  return blob ? decrypt(blob) : null;
}

export class ByoKeyRejectedError extends Error {}

/**
 * Light-probe the key against the provider's models endpoint so a typo or a
 * revoked key surfaces at save time instead of on the first analysis run.
 * Only the HTTP status is reported back — never the key.
 */
export async function probeByoApiKey(provider: ByoProvider, apiKey: string): Promise<void> {
  try {
    if (provider === "anthropic") {
      await new Anthropic({ apiKey, maxRetries: 0 }).models.list({ limit: 1 });
    } else {
      await new OpenAI({ apiKey, maxRetries: 0 }).models.list();
    }
  } catch (error) {
    const status = (error as { status?: number }).status;
    if (status === 401 || status === 403) {
      throw new ByoKeyRejectedError(`${PROVIDER_LABELS[provider]} rejected this API key (HTTP ${status}).`);
    }
    throw new ByoKeyRejectedError(
      `Could not verify the ${PROVIDER_LABELS[provider]} key${status ? ` (HTTP ${status})` : ""}. Check egress to the provider and try again.`,
    );
  }
}

export async function setByoApiKey(
  provider: ByoProvider,
  apiKey: string,
  updatedBy?: string,
  options: { probe?: boolean } = {},
): Promise<void> {
  const key = apiKey.trim();
  if (!key) throw new Error("API key must not be empty.");
  if (options.probe ?? true) await probeByoApiKey(provider, key);

  const hint = key.slice(-4);
  const encrypted = encrypt(key);
  await prisma.$transaction([
    prisma.appSetting.upsert({
      where: { key: byoSettingKey(provider, "apiKey") },
      create: { key: byoSettingKey(provider, "apiKey"), value: encrypted, updatedBy },
      update: { value: encrypted, updatedBy },
    }),
    prisma.appSetting.upsert({
      where: { key: byoSettingKey(provider, "keyHint") },
      create: { key: byoSettingKey(provider, "keyHint"), value: hint, updatedBy },
      update: { value: hint, updatedBy },
    }),
  ]);
}

/** Removes the key and its hint; a model override is kept for the next key. */
export async function clearByoApiKey(provider: ByoProvider): Promise<void> {
  await prisma.appSetting.deleteMany({
    where: { key: { in: [byoSettingKey(provider, "apiKey"), byoSettingKey(provider, "keyHint")] } },
  });
}

export async function setByoModel(
  provider: ByoProvider,
  model: string | null,
  updatedBy?: string,
): Promise<void> {
  const value = clean(model);
  const key = byoSettingKey(provider, "model");
  if (!value) {
    await prisma.appSetting.deleteMany({ where: { key } });
    return;
  }
  await prisma.appSetting.upsert({
    where: { key },
    create: { key, value, updatedBy },
    update: { value, updatedBy },
  });
}
