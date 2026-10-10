/**
 * Pure AI-engine selection rules — no Prisma, no SDKs, no env reads — so the
 * web tier and cna/ai_engine/chat_agent.py can be held to one shared vector
 * table (see ai-engine-rules.test.ts / tests/unit/test_chat_agent.py).
 *
 * The appliance's deploy-time AI mode (CNA_AI_MODE) decides which engine
 * family is allowed:
 *   saas     — the cloud-native engine for this appliance's cloud:
 *              azure-openai on Azure, bedrock on AWS.
 *   byo-api  — bring-your-own: anthropic and/or openai, keyed by an API key
 *              the admin entered on the AI Engine page.
 */

export type AiEngineId = "azure-openai" | "bedrock" | "anthropic" | "openai";
export type AiMode = "saas" | "byo-api";
export type ApplianceCloud = "azure" | "aws";
export type ByoProvider = "anthropic" | "openai";

export const VALID_ENGINES: ReadonlySet<AiEngineId> = new Set<AiEngineId>([
  "azure-openai",
  "bedrock",
  "anthropic",
  "openai",
]);

export const SAAS_ENGINE_BY_CLOUD: Readonly<Record<ApplianceCloud, AiEngineId>> = {
  azure: "azure-openai",
  aws: "bedrock",
};

// Ordered: the first entry is the deterministic tie-break when both BYO keys
// are configured and neither the stored setting nor the env default applies.
export const BYO_ENGINES: readonly ByoProvider[] = ["anthropic", "openai"];

export function clean(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  return trimmed.toLowerCase() === "none" ? "" : trimmed;
}

export function normalizeAiMode(value: string | null | undefined): AiMode {
  return clean(value) === "byo-api" ? "byo-api" : "saas";
}

export function normalizeApplianceCloud(value: string | null | undefined): ApplianceCloud {
  return clean(value) === "aws" ? "aws" : "azure";
}

export function normalizeAiEngine(value: string | null | undefined): AiEngineId | null {
  const normalized = clean(value) as AiEngineId;
  return VALID_ENGINES.has(normalized) ? normalized : null;
}

export function isByoProvider(value: string): value is ByoProvider {
  return (BYO_ENGINES as readonly string[]).includes(value);
}

export function allowedEngines(mode: AiMode, cloud: ApplianceCloud): readonly AiEngineId[] {
  return mode === "byo-api" ? BYO_ENGINES : [SAAS_ENGINE_BY_CLOUD[cloud]];
}

export class AiEngineUnavailableError extends Error {}

export type ResolveEngineInput = {
  mode: AiMode;
  cloud: ApplianceCloud;
  stored: string | null | undefined;
  envDefault: string | null | undefined;
  configured: ReadonlySet<AiEngineId>;
};

/**
 * Resolve the active engine — mirrors resolve_engine() in chat_agent.py.
 *
 * saas:    the single engine allowed for this cloud; stored/env preferences
 *          are irrelevant. Configuration is the caller's check.
 * byo-api: among configured BYO engines — one ⇒ it wins outright (stored
 *          setting ignored); two ⇒ stored, then env default, then anthropic;
 *          none ⇒ AiEngineUnavailableError.
 * A stored value from another mode is skipped, never fatal.
 */
export function resolveEngine(input: ResolveEngineInput): AiEngineId {
  const allowed = allowedEngines(input.mode, input.cloud);
  if (input.mode === "saas") return allowed[0];

  const candidates = allowed.filter((engine) => input.configured.has(engine));
  if (candidates.length === 0) {
    throw new AiEngineUnavailableError(
      "No bring-your-own AI API key is configured. Add an Anthropic or OpenAI key on the admin AI Engine page.",
    );
  }
  if (candidates.length === 1) return candidates[0];

  const stored = normalizeAiEngine(input.stored);
  if (stored && candidates.includes(stored)) return stored;
  const envDefault = normalizeAiEngine(input.envDefault);
  if (envDefault && candidates.includes(envDefault)) return envDefault;
  return candidates[0];
}

/** The BYO toggle is only meaningful when there is a real choice to make. */
export function byoToggleEnabled(configured: ReadonlySet<AiEngineId>): boolean {
  return BYO_ENGINES.every((engine) => configured.has(engine));
}
