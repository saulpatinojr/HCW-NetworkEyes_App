import Anthropic from "@anthropic-ai/sdk";
import {
  BedrockRuntimeClient,
  ConverseCommand,
  type Message as BedrockMessage,
} from "@aws-sdk/client-bedrock-runtime";
import { DefaultAzureCredential, getBearerTokenProvider } from "@azure/identity";
import OpenAI, { AzureOpenAI } from "openai";

import { prisma } from "@/lib/prisma";

import {
  type ByoCredentialPresence,
  emptyByoPresence,
  getByoCredentialPresence,
  getDecryptedByoApiKey,
  PROVIDER_LABELS,
} from "./ai-byo-credentials";
import {
  type AiEngineId,
  type AiMode,
  AiEngineUnavailableError,
  type ApplianceCloud,
  allowedEngines,
  BYO_ENGINES,
  byoToggleEnabled,
  clean,
  normalizeAiEngine,
  normalizeAiMode,
  normalizeApplianceCloud,
  resolveEngine,
  SAAS_ENGINE_BY_CLOUD,
  VALID_ENGINES,
} from "./ai-engine-rules";

export { AiEngineUnavailableError, normalizeAiEngine, VALID_ENGINES };
export type { AiEngineId, AiMode, ApplianceCloud, ByoCredentialPresence };

export const AI_ENGINE_SETTING_KEY = "ai.activeEngine";

export type AiChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

export type AiCompletionOptions = {
  messages: AiChatMessage[];
  maxCompletionTokens: number;
  responseFormat?: "json_object";
};

export type AiEngineStatus = {
  id: AiEngineId;
  label: string;
  description: string;
  configured: boolean;
  active: boolean;
  details: Array<{ label: string; value: string }>;
  missing: string[];
};

export type McpServerStatus = {
  id: string;
  label: string;
  endpoint: string;
  transport: string;
  configured: boolean;
};

const DEFAULT_AZURE_DEPLOYMENT = "gpt-chat-latest";
const DEFAULT_AZURE_API_VERSION = "2024-12-01-preview";
// Model ids are overridable (AppSetting ai.byo.<provider>.model, then env) so a
// deployment never edits code to move models. Keep in sync with chat_agent.py.
const DEFAULT_ANTHROPIC_MODEL = "claude-opus-5";
const DEFAULT_OPENAI_MODEL = "gpt-5.4";

const JSON_ONLY_INSTRUCTION = "Respond with a single valid JSON object and nothing else.";

function hostOnly(value: string): string {
  if (!value) return "Not configured";
  try {
    return new URL(value).host;
  } catch {
    return value;
  }
}

// ---------------------------------------------------------------------------
// Mode / cloud (env contract set by Terraform from the deploy `ai_mode` input)
// ---------------------------------------------------------------------------

export function getAiMode(): AiMode {
  return normalizeAiMode(process.env.CNA_AI_MODE);
}

export function getApplianceCloud(): ApplianceCloud {
  return normalizeApplianceCloud(process.env.CNA_APPLIANCE_CLOUD);
}

export function getConfiguredDefaultAiEngine(): AiEngineId {
  const allowed = allowedEngines(getAiMode(), getApplianceCloud());
  const fromEnv = normalizeAiEngine(process.env.CNA_AI_ENGINE_DEFAULT);
  return fromEnv && allowed.includes(fromEnv) ? fromEnv : allowed[0];
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

function bedrockModelId(): string {
  return clean(process.env.CNA_BEDROCK_INFERENCE_PROFILE_ARN) || clean(process.env.CNA_BEDROCK_MODEL_ID);
}

function byoModel(provider: "anthropic" | "openai", byo: ByoCredentialPresence): string {
  const fallback = provider === "anthropic" ? DEFAULT_ANTHROPIC_MODEL : DEFAULT_OPENAI_MODEL;
  const envName = provider === "anthropic" ? "CNA_ANTHROPIC_MODEL" : "CNA_OPENAI_MODEL";
  return byo[provider].model || clean(process.env[envName]) || fallback;
}

/** Engines usable right now — SaaS engines from env, BYO engines from stored keys. */
export function getConfiguredEngines(byo: ByoCredentialPresence): Set<AiEngineId> {
  const configured = new Set<AiEngineId>();
  if (clean(process.env.AZURE_OPENAI_ENDPOINT)) configured.add("azure-openai");
  if (bedrockModelId()) configured.add("bedrock");
  for (const provider of BYO_ENGINES) {
    if (byo[provider].configured) configured.add(provider);
  }
  return configured;
}

export function getMcpServerStatuses(): McpServerStatus[] {
  const azureEndpoint = clean(process.env.CNA_AZURE_MCP_ENDPOINT ?? process.env.AZURE_MCP_SERVER_URL);
  const awsEndpoint = clean(process.env.CNA_AWS_MCP_ENDPOINT ?? process.env.AWS_MCP_SERVER_URL);
  const drawioEndpoint = clean(process.env.CNA_DRAWIO_MCP_URL);

  return [
    {
      id: "azure-mcp",
      label: "Azure MCP",
      endpoint: azureEndpoint || "Not configured",
      transport: clean(process.env.CNA_AZURE_MCP_TRANSPORT) || "streamable-http",
      configured: Boolean(azureEndpoint),
    },
    {
      id: "aws-mcp",
      label: "AWS MCP",
      endpoint: awsEndpoint || "Not configured",
      transport: clean(process.env.CNA_AWS_MCP_TRANSPORT) || "streamable-http",
      configured: Boolean(awsEndpoint),
    },
    {
      id: "drawio-mcp",
      label: "draw.io MCP",
      endpoint: drawioEndpoint || "Not configured",
      transport: "http",
      configured: Boolean(drawioEndpoint),
    },
  ];
}

/**
 * Status cards for the engines the current mode allows. `byo` is pre-fetched
 * (see getByoCredentialPresence) so this stays synchronous and testable.
 */
export function getAiEngineStatuses(
  activeEngine: AiEngineId | null,
  byo: ByoCredentialPresence,
): AiEngineStatus[] {
  const configured = getConfiguredEngines(byo);
  const statuses: Record<AiEngineId, () => AiEngineStatus> = {
    "azure-openai": () => {
      const endpoint = clean(process.env.AZURE_OPENAI_ENDPOINT);
      const deployment = clean(process.env.AZURE_OPENAI_DEPLOYMENT) || DEFAULT_AZURE_DEPLOYMENT;
      return {
        id: "azure-openai",
        label: "Azure OpenAI",
        description:
          "SaaS engine on the Azure appliance. Terraform provisions the deployment, private networking, RBAC, and env vars; the app authenticates with its managed identity.",
        configured: configured.has("azure-openai"),
        active: activeEngine === "azure-openai",
        details: [
          { label: "Endpoint", value: hostOnly(endpoint) },
          { label: "Deployment", value: deployment },
          { label: "API version", value: clean(process.env.AZURE_OPENAI_API_VERSION) || DEFAULT_AZURE_API_VERSION },
          { label: "Authentication", value: "Managed identity" },
        ],
        missing: endpoint ? [] : ["AZURE_OPENAI_ENDPOINT"],
      };
    },
    bedrock: () => {
      const profile = clean(process.env.CNA_BEDROCK_INFERENCE_PROFILE_ARN);
      const model = clean(process.env.CNA_BEDROCK_MODEL_ID);
      return {
        id: "bedrock",
        label: "Amazon Bedrock",
        description:
          "SaaS engine on the AWS appliance. Terraform grants the task role bedrock:InvokeModel and provisions the inference profile; the app authenticates with the task role.",
        configured: configured.has("bedrock"),
        active: activeEngine === "bedrock",
        details: [
          { label: "Model", value: model || "Not configured" },
          { label: "Inference profile", value: profile || "None" },
          { label: "Region", value: clean(process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION) || "SDK default" },
          { label: "Authentication", value: "Task role" },
        ],
        missing: bedrockModelId() ? [] : ["CNA_BEDROCK_MODEL_ID"],
      };
    },
    anthropic: () => ({
      id: "anthropic",
      label: PROVIDER_LABELS.anthropic,
      description: "Bring-your-own Anthropic API key, entered here by an admin and stored encrypted.",
      configured: configured.has("anthropic"),
      active: activeEngine === "anthropic",
      details: [
        { label: "API key", value: byo.anthropic.hint ? `••••${byo.anthropic.hint}` : "Not configured" },
        { label: "Model", value: byoModel("anthropic", byo) },
        { label: "Authentication", value: "API key (admin-entered)" },
      ],
      missing: byo.anthropic.configured ? [] : ["Anthropic API key"],
    }),
    openai: () => ({
      id: "openai",
      label: PROVIDER_LABELS.openai,
      description: "Bring-your-own OpenAI API key, entered here by an admin and stored encrypted.",
      configured: configured.has("openai"),
      active: activeEngine === "openai",
      details: [
        { label: "API key", value: byo.openai.hint ? `••••${byo.openai.hint}` : "Not configured" },
        { label: "Model", value: byoModel("openai", byo) },
        { label: "Authentication", value: "API key (admin-entered)" },
      ],
      missing: byo.openai.configured ? [] : ["OpenAI API key"],
    }),
  };

  return allowedEngines(getAiMode(), getApplianceCloud()).map((id) => statuses[id]());
}

// ---------------------------------------------------------------------------
// Resolution
// ---------------------------------------------------------------------------

async function readStoredEngine(): Promise<string | null> {
  const setting = await prisma.appSetting.findUnique({
    where: { key: AI_ENGINE_SETTING_KEY },
    select: { value: true },
  });
  return setting?.value ?? null;
}

async function readByoPresence(): Promise<ByoCredentialPresence> {
  return getAiMode() === "byo-api" ? getByoCredentialPresence() : emptyByoPresence();
}

/** Active engine, or null when the mode allows nothing configured yet (byo-api with no key). */
export async function resolveActiveAiEngine(): Promise<AiEngineId | null> {
  const [stored, byo] = await Promise.all([readStoredEngine(), readByoPresence()]);
  try {
    return resolveEngine({
      mode: getAiMode(),
      cloud: getApplianceCloud(),
      stored,
      envDefault: process.env.CNA_AI_ENGINE_DEFAULT,
      configured: getConfiguredEngines(byo),
    });
  } catch (error) {
    if (error instanceof AiEngineUnavailableError) return null;
    throw error;
  }
}

export async function getActiveAiEngine(): Promise<AiEngineId> {
  const engine = await resolveActiveAiEngine();
  if (!engine) {
    throw new AiEngineUnavailableError(
      "No bring-your-own AI API key is configured. Add an Anthropic or OpenAI key on the admin AI Engine page.",
    );
  }
  return engine;
}

export async function setActiveAiEngine(engine: AiEngineId, updatedBy?: string): Promise<void> {
  if (!VALID_ENGINES.has(engine)) {
    throw new Error(`Unsupported AI engine: ${engine}`);
  }
  const allowed = allowedEngines(getAiMode(), getApplianceCloud());
  if (!allowed.includes(engine)) {
    throw new Error(`${engine} is not available in ${getAiMode()} mode on this appliance.`);
  }

  const byo = await readByoPresence();
  const status = getAiEngineStatuses(engine, byo).find((item) => item.id === engine);
  if (!status?.configured) {
    throw new Error(`${status?.label ?? engine} is not fully configured.`);
  }

  await prisma.appSetting.upsert({
    where: { key: AI_ENGINE_SETTING_KEY },
    create: {
      key: AI_ENGINE_SETTING_KEY,
      value: engine,
      updatedBy,
    },
    update: {
      value: engine,
      updatedBy,
    },
  });
}

export async function getAiEngineDashboardState(): Promise<{
  mode: AiMode;
  cloud: ApplianceCloud;
  saasEngine: AiEngineId;
  activeEngine: AiEngineId | null;
  defaultEngine: AiEngineId;
  engines: AiEngineStatus[];
  byo: ByoCredentialPresence;
  byoToggleEnabled: boolean;
  mcpServers: McpServerStatus[];
}> {
  const [activeEngine, byo] = await Promise.all([resolveActiveAiEngine(), readByoPresence()]);
  const cloud = getApplianceCloud();
  return {
    mode: getAiMode(),
    cloud,
    saasEngine: SAAS_ENGINE_BY_CLOUD[cloud],
    activeEngine,
    defaultEngine: getConfiguredDefaultAiEngine(),
    engines: getAiEngineStatuses(activeEngine, byo),
    byo,
    byoToggleEnabled: byoToggleEnabled(getConfiguredEngines(byo)),
    mcpServers: getMcpServerStatuses(),
  };
}

// ---------------------------------------------------------------------------
// Transports
// ---------------------------------------------------------------------------

function getAzureClient(): AzureOpenAI {
  const endpoint = clean(process.env.AZURE_OPENAI_ENDPOINT);
  if (!endpoint) throw new Error("AZURE_OPENAI_ENDPOINT is not set");

  const credential = new DefaultAzureCredential();
  const azureADTokenProvider = getBearerTokenProvider(
    credential,
    "https://cognitiveservices.azure.com/.default",
  );

  return new AzureOpenAI({
    endpoint,
    azureADTokenProvider,
    apiVersion: clean(process.env.AZURE_OPENAI_API_VERSION) || DEFAULT_AZURE_API_VERSION,
    deployment: clean(process.env.AZURE_OPENAI_DEPLOYMENT) || DEFAULT_AZURE_DEPLOYMENT,
  });
}

async function completeWithAzure(options: AiCompletionOptions): Promise<string> {
  const client = getAzureClient();
  const deployment = clean(process.env.AZURE_OPENAI_DEPLOYMENT) || DEFAULT_AZURE_DEPLOYMENT;

  const response = await client.chat.completions.create({
    model: deployment,
    messages: options.messages,
    response_format: options.responseFormat ? { type: options.responseFormat } : undefined,
    max_completion_tokens: options.maxCompletionTokens,
  });

  return response.choices[0]?.message?.content ?? "";
}

async function completeWithOpenAi(options: AiCompletionOptions, byo: ByoCredentialPresence): Promise<string> {
  const apiKey = await getDecryptedByoApiKey("openai");
  if (!apiKey) throw new AiEngineUnavailableError("OpenAI API key is not configured.");

  const client = new OpenAI({ apiKey });
  const response = await client.chat.completions.create({
    model: byoModel("openai", byo),
    messages: options.messages,
    response_format: options.responseFormat ? { type: options.responseFormat } : undefined,
    max_completion_tokens: options.maxCompletionTokens,
  });

  return response.choices[0]?.message?.content ?? "";
}

/** Split the OpenAI-style message list into a system prompt + alternating turns. */
function splitSystem(options: AiCompletionOptions): { system: string; turns: Array<{ role: "user" | "assistant"; content: string }> } {
  const systemParts = options.messages.filter((m) => m.role === "system").map((m) => m.content);
  if (options.responseFormat === "json_object") systemParts.push(JSON_ONLY_INSTRUCTION);
  const turns = options.messages
    .filter((m): m is AiChatMessage & { role: "user" | "assistant" } => m.role !== "system")
    .map((m) => ({ role: m.role, content: m.content }));
  if (turns.length === 0) turns.push({ role: "user", content: "" });
  return { system: systemParts.join("\n\n"), turns };
}

async function completeWithAnthropic(options: AiCompletionOptions, byo: ByoCredentialPresence): Promise<string> {
  const apiKey = await getDecryptedByoApiKey("anthropic");
  if (!apiKey) throw new AiEngineUnavailableError("Anthropic API key is not configured.");

  const { system, turns } = splitSystem(options);
  const client = new Anthropic({ apiKey });
  const response = await client.messages.create({
    model: byoModel("anthropic", byo),
    max_tokens: options.maxCompletionTokens,
    system: system || undefined,
    messages: turns,
  });

  if (response.stop_reason === "refusal") return "";
  return response.content
    .filter((block): block is Anthropic.TextBlock => block.type === "text")
    .map((block) => block.text)
    .join("");
}

async function completeWithBedrock(options: AiCompletionOptions): Promise<string> {
  const modelId = bedrockModelId();
  if (!modelId) throw new AiEngineUnavailableError("CNA_BEDROCK_MODEL_ID is not set");

  const { system, turns } = splitSystem(options);
  const client = new BedrockRuntimeClient({});
  const response = await client.send(
    new ConverseCommand({
      modelId,
      system: system ? [{ text: system }] : undefined,
      messages: turns.map((turn): BedrockMessage => ({ role: turn.role, content: [{ text: turn.content }] })),
      inferenceConfig: { maxTokens: options.maxCompletionTokens },
    }),
  );

  return (response.output?.message?.content ?? []).map((block) => block.text ?? "").join("");
}

export async function generateAiCompletion(options: AiCompletionOptions): Promise<string> {
  const engine = await getActiveAiEngine();
  const byo = await readByoPresence();

  switch (engine) {
    case "anthropic":
      return completeWithAnthropic(options, byo);
    case "openai":
      return completeWithOpenAi(options, byo);
    case "bedrock":
      return completeWithBedrock(options);
    default:
      if (!clean(process.env.AZURE_OPENAI_ENDPOINT)) {
        throw new AiEngineUnavailableError(
          "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT (and AZURE_OPENAI_DEPLOYMENT) before running analysis.",
        );
      }
      return completeWithAzure(options);
  }
}
