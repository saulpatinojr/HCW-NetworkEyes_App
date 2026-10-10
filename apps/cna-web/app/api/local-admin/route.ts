import { NextRequest, NextResponse } from "next/server";
import { randomBytes } from "crypto";
import { prisma } from "@/lib/prisma";
import { verifyLocalAdminPassword } from "@/lib/local-admin";
import { checkRateLimit } from "@/lib/rate-limit";

// Break-glass local admin sign-in. Isolated from NextAuth entirely — creates
// a Session row and sets the same cookie Auth.js already reads, so auth()
// and every existing role check work unchanged. Deliberately NOT a NextAuth
// Credentials provider: combining Credentials with the PrismaAdapter forces
// the whole app onto JWT sessions, which would change session/revocation
// behavior for every Entra ID user too. This keeps blast radius to zero.
const SESSION_COOKIE_NAME =
  process.env.NODE_ENV === "production" ? "__Secure-authjs.session-token" : "authjs.session-token";
const SESSION_DURATION_MS = 4 * 60 * 60 * 1000; // 4h — shorter-lived than a normal SSO session
const RATE_LIMIT_ATTEMPTS = 5;
const RATE_LIMIT_WINDOW_MS = 15 * 60 * 1000; // 15 minutes

function getClientIp(req: NextRequest): string {
  // Azure Front Door sets X-Azure-ClientIP itself from the TCP connection,
  // overwriting any client-supplied value — unlike X-Forwarded-For, whose
  // *first* hop is whatever the client sent and is trivially spoofable to
  // get a fresh rate-limit bucket per request. Fall back to a constant key
  // so a missing header still gets *some* rate limiting rather than none.
  // Known limitation: this is per-container-instance, not global across
  // replicas — acceptable for a first pass on a single shared secret.
  return req.headers.get("x-azure-clientip")?.trim() ?? "unknown";
}

export async function POST(req: NextRequest) {
  const ip = getClientIp(req);

  const allowed = await checkRateLimit(ip, "local-admin-login", RATE_LIMIT_ATTEMPTS, RATE_LIMIT_WINDOW_MS);
  if (!allowed) {
    console.warn("[local-admin] rate limited", { ip, timestamp: new Date().toISOString() });
    return NextResponse.json({ error: "Too many attempts" }, { status: 429 });
  }

  const body = await req.json().catch(() => null);
  const password = typeof body?.password === "string" ? body.password : "";

  const user = await prisma.user.findFirst({ where: { isLocalAdmin: true } });

  // Generic failure for both "no local admin configured" and "wrong password" —
  // never reveal which one, to avoid leaking whether the feature is even enabled.
  if (!user?.passwordHash || !password || !verifyLocalAdminPassword(password, user.passwordHash)) {
    console.warn("[local-admin] failed login attempt", { ip, timestamp: new Date().toISOString() });
    return NextResponse.json({ error: "Invalid password" }, { status: 401 });
  }

  const sessionToken = randomBytes(32).toString("hex");
  const expires = new Date(Date.now() + SESSION_DURATION_MS);

  await prisma.session.create({
    data: { sessionToken, userId: user.id, expires },
  });

  console.warn("[local-admin] successful login — break-glass account in use", {
    ip,
    userId: user.id,
    timestamp: new Date().toISOString(),
  });

  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE_NAME, sessionToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires,
  });

  return response;
}
