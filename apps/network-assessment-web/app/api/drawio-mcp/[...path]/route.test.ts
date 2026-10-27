import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { GET, POST } from "./route";

// Ticket #245: the draw.io tool route is internal only. It answers 401 unless the
// request carries the shared bearer (NETWORK_ASSESSMENT_API_TOKEN). The value below is a test
// placeholder, not a credential.
const TOKEN = "test-shared-token-not-a-secret";

function ctx(tool: string) {
  return { params: Promise.resolve({ path: [tool] }) };
}

function get(tool: string, authorization?: string): Promise<Response> {
  const headers: Record<string, string> = {};
  if (authorization) headers.Authorization = authorization;
  return GET(new Request(`http://localhost/api/drawio-mcp/${tool}`, { headers }), ctx(tool));
}

function post(tool: string, body: unknown, authorization?: string): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authorization) headers.Authorization = authorization;
  return POST(
    new Request(`http://localhost/api/drawio-mcp/${tool}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    }),
    ctx(tool),
  );
}

describe("/api/drawio-mcp requires the internal bearer", () => {
  const original = process.env.NETWORK_ASSESSMENT_API_TOKEN;

  beforeEach(() => {
    process.env.NETWORK_ASSESSMENT_API_TOKEN = TOKEN;
  });
  afterEach(() => {
    if (original === undefined) delete process.env.NETWORK_ASSESSMENT_API_TOKEN;
    else process.env.NETWORK_ASSESSMENT_API_TOKEN = original;
  });

  it("GET health without credentials is 401", async () => {
    const res = await get("health");
    expect(res.status).toBe(401);
    expect(res.headers.get("www-authenticate")).toBe("Bearer");
  });

  it("GET health with a wrong token is 401 and does not echo either token", async () => {
    const res = await get("health", "Bearer not-the-token");
    expect(res.status).toBe(401);
    const text = await res.text();
    expect(text).not.toContain(TOKEN);
    expect(text).not.toContain("not-the-token");
  });

  it("a non-Bearer scheme is 401", async () => {
    expect((await get("health", `Basic ${TOKEN}`)).status).toBe(401);
  });

  it("a token that is only a prefix of the right one is 401", async () => {
    expect((await get("health", `Bearer ${TOKEN.slice(0, -1)}`)).status).toBe(401);
  });

  it("GET health with the right token is 200", async () => {
    const res = await get("health", `Bearer ${TOKEN}`);
    expect(res.status).toBe(200);
    expect((await res.json()).status).toBe("ok");
  });

  it("POST without credentials is 401 and reaches no tool", async () => {
    const res = await post("create_diagram", { xml: "<mxfile></mxfile>" });
    expect(res.status).toBe(401);
  });

  it("POST with a wrong token is 401", async () => {
    const res = await post("search_shapes", { query: "vnet" }, "Bearer wrong");
    expect(res.status).toBe(401);
  });

  it("POST with the right token reaches the tool", async () => {
    const res = await post("create_diagram", { xml: "<mxfile></mxfile>" }, `Bearer ${TOKEN}`);
    expect(res.status).toBe(200);
    expect((await res.json()).tool).toBe("create_diagram");
  });

  it("fails closed: with no token configured even a bearer is refused", async () => {
    delete process.env.NETWORK_ASSESSMENT_API_TOKEN;
    expect((await get("health")).status).toBe(401);
    expect((await get("health", "Bearer ")).status).toBe(401);
    expect((await get("health", "Bearer anything")).status).toBe(401);
  });
});
