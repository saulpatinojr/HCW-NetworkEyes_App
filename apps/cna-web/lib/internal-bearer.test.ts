import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { hasValidInternalBearer } from "@/lib/internal-bearer";

const TOKEN = "test-shared-token-0123456789abcdef";

function request(authorization?: string): Request {
  return new Request("http://localhost/api/drawio-mcp/x", {
    headers: authorization === undefined ? {} : { authorization },
  });
}

describe("hasValidInternalBearer", () => {
  const saved = process.env.CNA_API_TOKEN;

  beforeEach(() => {
    process.env.CNA_API_TOKEN = TOKEN;
  });

  afterEach(() => {
    if (saved === undefined) delete process.env.CNA_API_TOKEN;
    else process.env.CNA_API_TOKEN = saved;
  });

  it("accepts the configured token, whatever the case of the scheme", () => {
    expect(hasValidInternalBearer(request(`Bearer ${TOKEN}`))).toBe(true);
    expect(hasValidInternalBearer(request(`bearer ${TOKEN}`))).toBe(true);
  });

  it("refuses a missing header, another scheme, a wrong token and a token of another length", () => {
    expect(hasValidInternalBearer(request())).toBe(false);
    expect(hasValidInternalBearer(request(TOKEN))).toBe(false);
    expect(hasValidInternalBearer(request(`Basic ${TOKEN}`))).toBe(false);
    expect(hasValidInternalBearer(request("Bearer wrong-token"))).toBe(false);
    expect(hasValidInternalBearer(request(`Bearer ${TOKEN}x`))).toBe(false);
    expect(hasValidInternalBearer(request(`Bearer ${TOKEN.slice(0, -1)}`))).toBe(false);
    expect(hasValidInternalBearer(request("Bearer "))).toBe(false);
  });

  it("fails closed when no token is configured, even for an empty bearer", () => {
    delete process.env.CNA_API_TOKEN;
    expect(hasValidInternalBearer(request(`Bearer ${TOKEN}`))).toBe(false);
    expect(hasValidInternalBearer(request("Bearer "))).toBe(false);
    process.env.CNA_API_TOKEN = "";
    expect(hasValidInternalBearer(request("Bearer "))).toBe(false);
  });
});
