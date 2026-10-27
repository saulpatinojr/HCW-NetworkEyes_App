import { describe, expect, it } from "vitest";

import {
  type AiEngineId,
  AiEngineUnavailableError,
  allowedEngines,
  byoToggleEnabled,
  normalizeAiEngine,
  normalizeAiMode,
  normalizeApplianceCloud,
  resolveEngine,
} from "./ai-engine-rules";

// Shared resolver vector table — mirrored by tests/unit/test_chat_agent.py
// RESOLVER_VECTORS. Keep the two in lockstep.
// [mode, cloud, stored, envDefault, configured, expected | null(=unavailable)]
const VECTORS: Array<
  ["saas" | "byo-api", "azure" | "aws", string | null, string | null, AiEngineId[], AiEngineId | null]
> = [
  // saas: one engine per cloud; stored/env preferences are irrelevant
  ["saas", "azure", null, null, ["azure-openai"], "azure-openai"],
  ["saas", "azure", "openai", "openai", ["azure-openai"], "azure-openai"],
  ["saas", "azure", "foundry-claude", null, ["azure-openai"], "azure-openai"],
  ["saas", "azure", "bogus", null, [], "azure-openai"],
  ["saas", "aws", null, null, ["bedrock"], "bedrock"],
  ["saas", "aws", "azure-openai", null, ["bedrock"], "bedrock"],
  // byo-api: no key -> unavailable
  ["byo-api", "azure", null, null, [], null],
  ["byo-api", "azure", "anthropic", null, [], null],
  ["byo-api", "azure", null, null, ["azure-openai"], null],
  // byo-api: exactly one key -> it wins, stored setting ignored
  ["byo-api", "azure", null, null, ["anthropic"], "anthropic"],
  ["byo-api", "azure", "openai", null, ["anthropic"], "anthropic"],
  ["byo-api", "aws", "azure-openai", "openai", ["openai"], "openai"],
  // byo-api: both keys -> stored, then env default, then anthropic
  ["byo-api", "azure", "openai", null, ["anthropic", "openai"], "openai"],
  ["byo-api", "azure", "anthropic", "openai", ["anthropic", "openai"], "anthropic"],
  ["byo-api", "azure", null, "openai", ["anthropic", "openai"], "openai"],
  ["byo-api", "azure", "azure-openai", "openai", ["anthropic", "openai"], "openai"],
  ["byo-api", "azure", "bogus", "bogus", ["anthropic", "openai"], "anthropic"],
  ["byo-api", "azure", null, null, ["anthropic", "openai"], "anthropic"],
];

describe("resolveEngine", () => {
  it.each(VECTORS)("%s/%s stored=%s env=%s configured=%j -> %s", (mode, cloud, stored, envDefault, configured, expected) => {
    const input = { mode, cloud, stored, envDefault, configured: new Set(configured) };
    if (expected === null) {
      expect(() => resolveEngine(input)).toThrow(AiEngineUnavailableError);
    } else {
      expect(resolveEngine(input)).toBe(expected);
    }
  });
});

describe("normalisation", () => {
  it("defaults mode/cloud when unset or unknown", () => {
    expect(normalizeAiMode(undefined)).toBe("saas");
    expect(normalizeAiMode("BYO-API")).toBe("saas");
    expect(normalizeAiMode(" byo-api ")).toBe("byo-api");
    expect(normalizeApplianceCloud(undefined)).toBe("azure");
    expect(normalizeApplianceCloud("aws")).toBe("aws");
    expect(normalizeApplianceCloud("gcp")).toBe("azure");
  });

  it("rejects unknown engine ids and treats 'none' as unset", () => {
    expect(normalizeAiEngine("anthropic")).toBe("anthropic");
    expect(normalizeAiEngine("bedrock")).toBe("bedrock");
    expect(normalizeAiEngine("foundry-claude")).toBeNull();
    expect(normalizeAiEngine("none")).toBeNull();
    expect(normalizeAiEngine(null)).toBeNull();
  });
});

describe("allowedEngines / toggle", () => {
  it("allows one saas engine per cloud and both byo engines", () => {
    expect(allowedEngines("saas", "azure")).toEqual(["azure-openai"]);
    expect(allowedEngines("saas", "aws")).toEqual(["bedrock"]);
    expect(allowedEngines("byo-api", "azure")).toEqual(["anthropic", "openai"]);
  });

  it("enables the toggle only when both byo keys are configured", () => {
    expect(byoToggleEnabled(new Set())).toBe(false);
    expect(byoToggleEnabled(new Set<AiEngineId>(["anthropic"]))).toBe(false);
    expect(byoToggleEnabled(new Set<AiEngineId>(["anthropic", "openai"]))).toBe(true);
    expect(byoToggleEnabled(new Set<AiEngineId>(["azure-openai", "openai"]))).toBe(false);
  });
});
