import { afterEach, describe, expect, it, vi } from "vitest";

// ai-engine.ts builds its database client when it is imported. The status cards read no database,
// so a stand-in keeps this test free of a generated Prisma client.
vi.mock("@/lib/prisma", () => ({ prisma: {} }));

import { emptyByoPresence } from "./ai-byo-credentials";
import { getAiEngineStatuses } from "./ai-engine";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getAiEngineStatuses wording", () => {
  it.each([
    ["azure", "azure-openai", "SaaS engine for a deployment on Azure."],
    ["aws", "bedrock", "SaaS engine for a deployment on AWS."],
  ] as const)("describes the %s SaaS engine without the word 'edition'", (cloud, id, opening) => {
    vi.stubEnv("NETWORK_ASSESSMENT_AI_MODE", "saas");
    vi.stubEnv("NETWORK_ASSESSMENT_APPLIANCE_CLOUD", cloud);

    const statuses = getAiEngineStatuses(null, emptyByoPresence());
    const status = statuses.find((s) => s.id === id);

    expect(status).toBeDefined();
    expect(status?.description).toContain(opening);
    expect(status?.description).not.toMatch(/edition/i);
  });
});
