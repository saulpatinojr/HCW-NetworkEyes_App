import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiHeaders, internalApiHeaders, resetInternalApiTokenCache } from "./api-client";

describe("apiHeaders", () => {
  const original = process.env.CNA_API_TOKEN;

  beforeEach(() => {
    delete process.env.CNA_API_TOKEN;
  });
  afterEach(() => {
    if (original === undefined) delete process.env.CNA_API_TOKEN;
    else process.env.CNA_API_TOKEN = original;
  });

  it("adds a Bearer Authorization header when CNA_API_TOKEN is set", () => {
    process.env.CNA_API_TOKEN = "s3cret-token";
    expect(apiHeaders()).toEqual({ Authorization: "Bearer s3cret-token" });
  });

  it("omits the Authorization header when CNA_API_TOKEN is unset (local dev)", () => {
    expect(apiHeaders()).toEqual({});
    expect(apiHeaders({ "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
    });
  });

  it("merges caller-supplied headers with the Authorization header", () => {
    process.env.CNA_API_TOKEN = "abc";
    expect(apiHeaders({ "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer abc",
    });
  });

  it("lets an explicit Authorization override be replaced by the token", () => {
    process.env.CNA_API_TOKEN = "real";
    // The token is authoritative: a caller cannot smuggle a different bearer.
    expect(apiHeaders({ Authorization: "Bearer fake" })).toEqual({
      Authorization: "Bearer real",
    });
  });

  it("does not mutate the caller's header object", () => {
    process.env.CNA_API_TOKEN = "t";
    const extra = { "Content-Type": "application/json" };
    apiHeaders(extra);
    expect(extra).toEqual({ "Content-Type": "application/json" });
  });
});

describe("internalApiHeaders", () => {
  const originalToken = process.env.CNA_API_TOKEN;
  const originalAudience = process.env.CNA_ENTRA_AUDIENCE;

  beforeEach(() => {
    delete process.env.CNA_API_TOKEN;
    delete process.env.CNA_ENTRA_AUDIENCE;
    resetInternalApiTokenCache();
  });
  afterEach(() => {
    if (originalToken === undefined) delete process.env.CNA_API_TOKEN;
    else process.env.CNA_API_TOKEN = originalToken;
    if (originalAudience === undefined) delete process.env.CNA_ENTRA_AUDIENCE;
    else process.env.CNA_ENTRA_AUDIENCE = originalAudience;
    resetInternalApiTokenCache();
  });

  it("falls back to the shared token when no Entra audience is configured", async () => {
    process.env.CNA_API_TOKEN = "shared";
    const acquire = async () => {
      throw new Error("must not be called");
    };
    expect(await internalApiHeaders({ "Content-Type": "application/json" }, acquire)).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer shared",
    });
  });

  it("obtains an Entra token for the audience's /.default scope", async () => {
    process.env.CNA_ENTRA_AUDIENCE = "api://cna-api-test";
    const scopes: string[] = [];
    const acquire = async (scope: string) => {
      scopes.push(scope);
      return { token: "entra-token", expiresOnTimestamp: Date.now() + 60 * 60 * 1000 };
    };
    expect(await internalApiHeaders({ "Content-Type": "application/json" }, acquire)).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer entra-token",
    });
    expect(scopes).toEqual(["api://cna-api-test/.default"]);
  });

  it("the Entra token wins over the shared token on an internal route", async () => {
    process.env.CNA_API_TOKEN = "shared";
    process.env.CNA_ENTRA_AUDIENCE = "api://cna-api-test";
    const acquire = async () => ({ token: "entra-token", expiresOnTimestamp: Date.now() + 3_600_000 });
    expect(await internalApiHeaders(undefined, acquire)).toEqual({ Authorization: "Bearer entra-token" });
  });

  it("caches the token until five minutes before expiry", async () => {
    process.env.CNA_ENTRA_AUDIENCE = "api://cna-api-test";
    let calls = 0;
    const longLived = async () => {
      calls += 1;
      return { token: `t${calls}`, expiresOnTimestamp: Date.now() + 3_600_000 };
    };
    await internalApiHeaders(undefined, longLived);
    await internalApiHeaders(undefined, longLived);
    expect(calls).toBe(1);

    resetInternalApiTokenCache();
    const nearlyExpired = async () => {
      calls += 1;
      return { token: `t${calls}`, expiresOnTimestamp: Date.now() + 60_000 };
    };
    await internalApiHeaders(undefined, nearlyExpired);
    await internalApiHeaders(undefined, nearlyExpired);
    expect(calls).toBe(3);
  });
});
