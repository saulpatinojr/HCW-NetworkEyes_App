import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Auth.js v5 with PrismaAdapter (database sessions) cannot run in Edge Runtime.
// Importing `auth` from "@/lib/auth" here would instantiate PrismaClient in
// Edge Runtime, which is unsupported and causes UnknownAction errors.
//
// Pattern: use a lightweight cookie-presence check here (UX redirect only).
// Real session validation (DB lookup) happens in server components via auth()
// running in Node.js runtime. The middleware is NOT the security gate — server
// components are. This matches the Auth.js v5 recommended pattern for
// database-session adapters.
export function middleware(req: NextRequest) {
  // OWA-01: Generate a unique nonce for script elements
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isProd = process.env.NODE_ENV === "production";
  const scriptCsp = isProd ? `'nonce-${nonce}'` : `'unsafe-inline' 'unsafe-eval'`;

  const cspHeader = `
    default-src 'self';
    script-src 'self' ${scriptCsp};
    style-src 'self' 'unsafe-inline';
    img-src 'self' data:;
    font-src 'self';
    connect-src 'self' https://login.microsoftonline.com https://*.openai.azure.com;
    frame-src 'self' https://embed.diagrams.net;
    frame-ancestors 'none';
    object-src 'none';
    upgrade-insecure-requests;
  `.replace(/\s{2,}/g, " ").trim();

  // Pass nonce to Next.js components via request headers
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", cspHeader);

  const isDashboard = req.nextUrl.pathname.startsWith("/dashboard");
  if (isDashboard) {
    // Auth.js v5 sets __Secure-authjs.session-token in HTTPS contexts (AFD).
    // OWA-04: The non-Secure prefix fallback is restricted to non-production to prevent
    // a forged or expired non-Secure cookie from bypassing the redirect guard in production.
    // Real session validation (DB lookup) always happens in server components regardless.
    const hasSession =
      req.cookies.has("__Secure-authjs.session-token") ||
      (process.env.NODE_ENV !== "production" &&
        req.cookies.has("authjs.session-token"));

    if (!hasSession) {
      const signinUrl = new URL("/auth/signin", req.url);
      return NextResponse.redirect(signinUrl);
    }
  }

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
  response.headers.set("Content-Security-Policy", cspHeader);
  return response;
}

export const config = {
  // Match all routes except API, Next.js internals, and static assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
