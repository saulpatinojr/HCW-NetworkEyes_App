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
