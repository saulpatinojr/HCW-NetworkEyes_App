import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

// Proxy to the cna-api chat router (Phase G). Auth + membership are enforced
// here; the internal API is only reachable server-side via CNA_API_INTERNAL_URL
// (same pattern as lib/metrics-api.ts).

type ChatMessage = { role: "user" | "assistant"; content: string };

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const session = await auth();
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;

  const engagement = await prisma.engagement.findUnique({
    where: { id },
    include: { members: true },
  });
  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  const isMember = engagement.members.some((m) => m.userId === session.user!.id);
  if (!isMember) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const apiUrl = process.env.CNA_API_INTERNAL_URL;
  if (!apiUrl) {
    return NextResponse.json(
      { error: "Copilot backend is not configured (CNA_API_INTERNAL_URL unset)." },
      { status: 503 },
    );
  }

  let messages: ChatMessage[];
  try {
    const body = (await req.json()) as { messages?: ChatMessage[] };
    messages = (body.messages ?? []).filter(
      (m) => (m.role === "user" || m.role === "assistant") && typeof m.content === "string",
    );
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  if (messages.length === 0) {
    return NextResponse.json({ error: "messages must not be empty" }, { status: 422 });
  }

  try {
    const res = await fetch(`${apiUrl}/chat/${encodeURIComponent(id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
      cache: "no-store",
      signal: AbortSignal.timeout(90_000),
    });

    const data: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const detail =
        data && typeof data === "object" && "detail" in data
          ? String((data as { detail: unknown }).detail)
          : `Copilot request failed (${res.status})`;
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json(
      { error: "Copilot backend is unreachable. Try again shortly." },
      { status: 502 },
    );
  }
}
