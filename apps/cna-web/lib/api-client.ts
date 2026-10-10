// Server-side helper for calling the internal cna-api (CNA_API_INTERNAL_URL).
// Every web→api request must carry the shared bearer token when one is
// configured (SEC-001 / ARCH-002): the api enforces `Authorization: Bearer
// <CNA_API_TOKEN>` on every path except /health and /ready. The token is a
// runtime secret injected by the appliances' Terraform onto both containers;
// it is never logged and never returned to a client.

/**
 * Build the headers for an internal cna-api request. Merges any caller-supplied
 * headers (e.g. `Content-Type`) with the `Authorization` header when
 * `CNA_API_TOKEN` is set. When the token is unset (local dev), no Authorization
 * header is added and the api falls back to unauthenticated mode.
 */
export function apiHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra ?? {}) };
  const token = process.env.CNA_API_TOKEN;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}
