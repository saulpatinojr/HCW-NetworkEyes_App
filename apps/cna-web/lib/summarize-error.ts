// Condense raw ARM/SDK error text into one readable sentence for the UI.
// The full raw text remains in the database record / server logs.
export function summarizeErrorText(reason: string): string {
  let text = reason;
  try {
    const parsed = JSON.parse(reason) as { error?: { message?: string }; message?: string };
    const m = parsed?.error?.message ?? parsed?.message;
    if (typeof m === "string" && m.trim()) text = m;
  } catch {
    /* not JSON — use as-is */
  }
  if (/AuthorizationFailed|does not have authorization/i.test(text)) {
    return "Access denied by Azure — grant the service principal Reader on this subscription, then re-run discovery.";
  }
  const firstLine = text.split("\n")[0].trim();
  return firstLine.length > 220 ? `${firstLine.slice(0, 220)}…` : firstLine;
}
