import { NextResponse } from "next/server";
import {
  createDiagram,
  listIconLibs,
  searchShapes,
} from "@/lib/drawio-mcp/server";
import { isAllowedStyle } from "@/lib/drawio-mcp/allow-list";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface RouteCtx {
  params: Promise<{ path: string[] }>;
}

function json(body: unknown, status = 200): NextResponse {
  return NextResponse.json(body, { status });
}

export async function GET(_req: Request, ctx: RouteCtx): Promise<NextResponse> {
  const { path } = await ctx.params;
  const tool = path?.[0] ?? "";

  if (tool === "health") {
    return json({ status: "ok", libs: listIconLibs() });
  }
  if (tool === "icon_libs") {
    return json({ libs: listIconLibs() });
  }
  return json({ error: `unknown tool: ${tool}` }, 404);
}

export async function POST(req: Request, ctx: RouteCtx): Promise<NextResponse> {
  const { path } = await ctx.params;
  const tool = path?.[0] ?? "";

  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return json({ error: "invalid json body" }, 400);
  }

  try {
    if (tool === "search_shapes") {
      const query = typeof body.query === "string" ? body.query : "";
      const limit = typeof body.limit === "number" ? body.limit : 20;
      if (!query.trim()) return json({ error: "query is required" }, 400);
      const hits = await searchShapes(query, limit);
      // Triple-enforce the allow-list at the response boundary.
      const filtered = hits.filter((h) => isAllowedStyle(h.style));
      return json({ tool, hits: filtered });
    }

    if (tool === "create_diagram") {
      const xml = typeof body.xml === "string" ? body.xml : "";
      const name = typeof body.name === "string" ? body.name : undefined;
      if (!xml) return json({ error: "xml is required" }, 400);
      const result = createDiagram(xml, name);
      return json({ tool, ...result });
    }

    return json({ error: `unknown tool: ${tool}` }, 404);
  } catch (err) {
    const message = err instanceof Error ? err.message : "internal error";
    return json({ error: message }, 500);
  }
}
