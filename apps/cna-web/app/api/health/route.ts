import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

// /api/health — liveness + readiness probe for Azure Container Apps.
// Returns 200 only when the process is up AND the database is reachable.
// The probe path in compute/main.tf and Terraform Front Door health probe
// both point here.
export async function GET() {
  const checks: Record<string, "ok" | "error"> = {
    process: "ok",
    database: "error",
  };

  try {
    // Lightweight query — avoids a full table scan.
    await prisma.$queryRaw`SELECT 1`;
    checks.database = "ok";
  } catch {
    // Return 503 so Container Apps marks the revision unhealthy and stops
    // routing traffic to a broken instance.
    return NextResponse.json(
      { status: "unhealthy", checks },
      { status: 503 }
    );
  }

  return NextResponse.json(
    { status: "healthy", checks },
    {
      status: 200,
      headers: {
        // Prevent Front Door or CDN from caching health responses.
        "Cache-Control": "no-store",
      },
    }
  );
}
