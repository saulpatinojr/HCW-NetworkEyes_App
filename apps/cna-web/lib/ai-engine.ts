import { DefaultAzureCredential, getBearerTokenProvider } from "@azure/identity";
import { AzureOpenAI } from "openai";

import { prisma } from "@/lib/prisma";

export const AI_ENGINE_SETTING_KEY = "ai.activeEngine";

export type AiEngineId = "azure-openai";

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

const VALID_ENGINES = new Set<AiEngineId>(["azure-openai"]);

function clean(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? "";
  return trimmed.toLowerCase() === "none" ? "" : trimmed;
}

function hostOnly(value: string): string {
  if (!value) return "Not configured";
  try {
    return new URL(value).host;
  } catch {
    return value;
  }
}

export function normalizeAiEngine(value: string | null | undefined): AiEngineId | null {
  const normalized = clean(value) as AiEngineId;
  return VALID_ENGINES.has(normalized) ? normalized : null;
}

export function getConfiguredDefaultAiEngine(): AiEngineId {
  // Azure OpenAI (gpt-chat-latest on the AIServices account) is the only
  // supported provider. Anthropic/Claude on Foundry was removed — it has no
  // model deployment in this tenant (see docs/adr/0001).
  return normalizeAiEngine(process.env.CNA_AI_ENGINE_DEFAULT) ?? "azure-openai";
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

export function getAiEngineStatuses(activeEngine: AiEngineId): AiEngineStatus[] {
  const azureEndpoint = clean(process.env.AZURE_OPENAI_ENDPOINT);
  const azureDeployment = clean(process.env.AZURE_OPENAI_DEPLOYMENT) || DEFAULT_AZURE_DEPLOYMENT;
  const azureApiVersion = clean(process.env.AZURE_OPENAI_API_VERSION) || DEFAULT_AZURE_API_VERSION;

  return [
    {
      id: "azure-openai",
      label: "Azure OpenAI",
      description: "Primary GenAI engine. Terraform provisions the deployment, private networking, RBAC, and env vars; the app authenticates with its managed identity.",
      configured: Boolean(azureEndpoint && azureDeployment),
      active: activeEngine === "azure-openai",
      details: [
        { label: "Endpoint", value: hostOnly(azureEndpoint) },
        { label: "Deployment", value: azureDeployment },
        { label: "API version", value: azureApiVersion },
        { label: "Authentication", value: "Managed identity" },
      ],
      missing: [
        ...(!azureEndpoint ? ["AZURE_OPENAI_ENDPOINT"] : []),
        ...(!azureDeployment ? ["AZURE_OPENAI_DEPLOYMENT"] : []),
      ],
    },
  ];
}

export async function getActiveAiEngine(): Promise<AiEngineId> {
  const setting = await prisma.appSetting.findUnique({
    where: { key: AI_ENGINE_SETTING_KEY },
    select: { value: true },
  });

  const stored = normalizeAiEngine(setting?.value);
  if (stored) return stored;

  return getConfiguredDefaultAiEngine();
}

export async function setActiveAiEngine(engine: AiEngineId, updatedBy?: string): Promise<void> {
  if (!VALID_ENGINES.has(engine)) {
    throw new Error(`Unsupported AI engine: ${engine}`);
  }

  const status = getAiEngineStatuses(engine).find((item) => item.id === engine);
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
  activeEngine: AiEngineId;
  defaultEngine: AiEngineId;
  engines: AiEngineStatus[];
  mcpServers: McpServerStatus[];
}> {
  const activeEngine = await getActiveAiEngine();
  return {
    activeEngine,
    defaultEngine: getConfiguredDefaultAiEngine(),
    engines: getAiEngineStatuses(activeEngine),
    mcpServers: getMcpServerStatuses(),
  };
}

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

export async function generateAiCompletion(options: AiCompletionOptions): Promise<string> {
  const activeEngine = await getActiveAiEngine();
  const statuses = getAiEngineStatuses(activeEngine);
  const activeStatus = statuses.find((item) => item.id === activeEngine);

  if (activeStatus?.configured) {
    return completeWithAzure(options);
  }

  const fallback = statuses.find((item) => item.configured);
  if (fallback?.id === "azure-openai") return completeWithAzure(options);

  throw new Error("Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT (and AZURE_OPENAI_DEPLOYMENT) before running analysis.");
}
