// Runs once when the server starts, before any request is handled (Next.js `register` hook): accept the old
// CNA_<NAME> setting names for a while by copying each one to NETWORK_ASSESSMENT_<NAME> when that is not set.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { adoptLegacyEnvironment } = await import("./lib/legacy-env");
    adoptLegacyEnvironment();
  }
}

// Server-side error reporting (Next.js `onRequestError` hook).
// Production builds redact Server Component errors in the browser and replace
// them with a digest; this hook logs the full error + digest to stderr as one
// JSON line so Container Apps / Log Analytics can correlate the digest a user
// reports with the real message.
export async function onRequestError(
  err: unknown,
  request: { path: string; method: string },
  context: { routerKind: string; routePath: string; routeType: string },
) {
  const error = err instanceof Error ? err : new Error(String(err));
  console.error(
    JSON.stringify({
      level: "error",
      source: "onRequestError",
      message: error.message,
      digest: (error as Error & { digest?: string }).digest,
      stack: error.stack,
      path: request.path,
      method: request.method,
      route: context.routePath,
      routeType: context.routeType,
    }),
  );
}
