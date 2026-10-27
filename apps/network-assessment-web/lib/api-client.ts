// Server-side helper for calling the internal network-assessment-api (NETWORK_ASSESSMENT_API_INTERNAL_URL).
// Every web→api request must carry a bearer when one is configured (SEC-001 /
// ARCH-002): the api enforces `Authorization: Bearer <NETWORK_ASSESSMENT_API_TOKEN>` on every
// path except /health and /ready. The token is a runtime secret supplied by the
// deployment to both containers; it is never logged and never returned to a
// client.
//
// The internal routes (/discovery/*, /intake, /publish) additionally accept an
// Entra access token for the api's app registration (change set H): when
// NETWORK_ASSESSMENT_ENTRA_AUDIENCE is set, `internalApiHeaders` obtains one with the web
// tier's own managed identity (AZURE_CLIENT_ID) and the api checks its
// signature, audience and the `Discovery.Run` app role. Nothing here turns
// authentication off; an unset audience simply falls back to the shared token.

/**
 * Build the headers for an internal network-assessment-api request. Merges any caller-supplied
 * headers (e.g. `Content-Type`) with the `Authorization` header when
 * `NETWORK_ASSESSMENT_API_TOKEN` is set. When the token is unset (local dev), no Authorization
 * header is added and the api falls back to unauthenticated mode.
 */
export function apiHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra ?? {}) };
  const token = process.env.NETWORK_ASSESSMENT_API_TOKEN;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

/** What a token acquirer returns: the bearer and its expiry (epoch ms). */
export type AcquiredToken = { token: string; expiresOnTimestamp: number };
export type TokenAcquirer = (scope: string) => Promise<AcquiredToken>;

// One cached token per process; refreshed five minutes before it expires.
const REFRESH_MARGIN_MS = 5 * 60 * 1000;
let cachedToken: (AcquiredToken & { audience: string }) | null = null;

async function acquireEntraToken(scope: string): Promise<AcquiredToken> {
  const { DefaultAzureCredential, ManagedIdentityCredential } = await import("@azure/identity");
  const clientId = process.env.AZURE_CLIENT_ID;
  // In a deployment the identity is the user-assigned one attached to the
  // container; locally `az login` through the default chain stands in for it.
  const credential = clientId
    ? new ManagedIdentityCredential(clientId)
    : new DefaultAzureCredential();
  const result = await credential.getToken(scope);
  if (!result) {
    throw new Error("the identity returned no token for the API audience");
  }
  return { token: result.token, expiresOnTimestamp: result.expiresOnTimestamp };
}

/**
 * Headers for a call to an internal network-assessment-api route. With `NETWORK_ASSESSMENT_ENTRA_AUDIENCE`
 * set the Authorization header carries an Entra token for that audience;
 * otherwise it is `apiHeaders(extra)` (the shared token, or nothing locally).
 */
export async function internalApiHeaders(
  extra?: Record<string, string>,
  acquire: TokenAcquirer = acquireEntraToken,
): Promise<Record<string, string>> {
  const audience = process.env.NETWORK_ASSESSMENT_ENTRA_AUDIENCE;
  if (!audience) {
    return apiHeaders(extra);
  }
  const now = Date.now();
  if (
    cachedToken === null ||
    cachedToken.audience !== audience ||
    cachedToken.expiresOnTimestamp - REFRESH_MARGIN_MS <= now
  ) {
    const scope = audience.endsWith("/.default") ? audience : `${audience}/.default`;
    const acquired = await acquire(scope);
    cachedToken = { audience, ...acquired };
  }
  return { ...(extra ?? {}), Authorization: `Bearer ${cachedToken.token}` };
}

/** Test seam: forget the cached token. */
export function resetInternalApiTokenCache(): void {
  cachedToken = null;
}
