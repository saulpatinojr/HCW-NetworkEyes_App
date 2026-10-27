import { afterEach, describe, expect, it, vi } from "vitest";

import { register } from "../instrumentation";
import { adoptLegacyEnvironment } from "./legacy-env";

describe("adoptLegacyEnvironment", () => {
  it("copies an old name to the new name when the new one is not set", () => {
    const env: Record<string, string | undefined> = { CNA_API_TOKEN: "a-token" };
    expect(adoptLegacyEnvironment(env)).toEqual(["NETWORK_ASSESSMENT_API_TOKEN"]);
    expect(env.NETWORK_ASSESSMENT_API_TOKEN).toBe("a-token");
    expect(env.CNA_API_TOKEN).toBe("a-token");
  });

  it("lets the new name win when both are set", () => {
    const env: Record<string, string | undefined> = {
      CNA_AI_MODE: "saas",
      NETWORK_ASSESSMENT_AI_MODE: "byo-api",
    };
    expect(adoptLegacyEnvironment(env)).toEqual([]);
    expect(env.NETWORK_ASSESSMENT_AI_MODE).toBe("byo-api");
  });

  it("counts an empty new value as set", () => {
    const env: Record<string, string | undefined> = {
      CNA_LOG_LEVEL: "DEBUG",
      NETWORK_ASSESSMENT_LOG_LEVEL: "",
    };
    expect(adoptLegacyEnvironment(env)).toEqual([]);
    expect(env.NETWORK_ASSESSMENT_LOG_LEVEL).toBe("");
  });

  it("ignores names without the old prefix, the bare prefix and unset values", () => {
    const env: Record<string, string | undefined> = {
      OTHER_CNA_THING: "x",
      CNA_: "bare",
      CNA_UNSET: undefined,
      XCNA_API_TOKEN: "y",
    };
    expect(adoptLegacyEnvironment(env)).toEqual([]);
    expect(Object.keys(env).filter((k) => k.startsWith("NETWORK_ASSESSMENT_"))).toEqual([]);
  });

  it("returns names, sorted, and never a value", () => {
    const env: Record<string, string | undefined> = { CNA_B: "secret-b", CNA_A: "secret-a" };
    const names = adoptLegacyEnvironment(env);
    expect(names).toEqual(["NETWORK_ASSESSMENT_A", "NETWORK_ASSESSMENT_B"]);
    expect(JSON.stringify(names)).not.toContain("secret");
  });
});

describe("register (the server start-up hook)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    delete process.env.NETWORK_ASSESSMENT_API_INTERNAL_URL;
  });

  it("adopts the old names in the Node.js runtime", async () => {
    vi.stubEnv("NEXT_RUNTIME", "nodejs");
    vi.stubEnv("CNA_API_INTERNAL_URL", "http://api.internal:8080");
    await register();
    expect(process.env.NETWORK_ASSESSMENT_API_INTERNAL_URL).toBe("http://api.internal:8080");
  });

  it("does nothing in the edge runtime", async () => {
    vi.stubEnv("NEXT_RUNTIME", "edge");
    vi.stubEnv("CNA_API_INTERNAL_URL", "http://api.internal:8080");
    await register();
    expect(process.env.NETWORK_ASSESSMENT_API_INTERNAL_URL).toBeUndefined();
  });
});
