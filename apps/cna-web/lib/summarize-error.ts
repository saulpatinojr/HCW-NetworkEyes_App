// Condense raw ARM/SDK/backend error text into one readable sentence for the UI.
// The full raw text remains in the database record / server logs; this helper is
// the single web-side boundary that guarantees client surfaces never render an
// unbounded, multi-line raw exception dump (Requirement 2.3, app-typescript area).
const MAX_LEN = 220;

export function summarizeErrorText(reason: string): string {
  let text = reason;
  try {
    const parsed = JSON.parse(reason) as { error?: { message?: string }; message?: string; detail?: string };
    const m = parsed?.error?.message ?? parsed?.message ?? parsed?.detail;
    if (typeof m === "string" && m.trim()) text = m;
  } catch {
    /* not JSON — use as-is */
  }
  if (/AuthorizationFailed|does not have authorization/i.test(text)) {
    return "Access denied by Azure — grant the service principal Reader on this subscription, then re-run discovery.";
  }
  const firstLine = text.split("\n")[0].trim();
  return firstLine.length > MAX_LEN ? `${firstLine.slice(0, MAX_LEN)}…` : firstLine;
}

// Sanitize a backend-supplied `detail` string before it reaches a client surface.
// The internal API sanitizes its own error paths, but the web layer must not
// trust that unconditionally: any raw multi-line SDK text or over-long detail is
// collapsed to a single bounded line, and empty/whitespace detail falls back to
// the caller's generic message. Full detail stays in the server logs upstream.
export function sanitizeBackendDetail(
  detail: string | null | undefined,
  fallback: string,
): string {
  if (typeof detail !== "string" || !detail.trim()) return fallback;
  return summarizeErrorText(detail);
}
