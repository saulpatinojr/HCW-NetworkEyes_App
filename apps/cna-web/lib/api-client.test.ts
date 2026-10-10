import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiHeaders } from "./api-client";

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
