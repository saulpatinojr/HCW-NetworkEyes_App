// ──────────────────────────────────────────────────────────────────────────────
// Server-side client for the cna-api metrics router (Phase C).
// Returns pre-aggregated StatMasterRecords; callers fall back to the
// client-side deriveStatMasters() when the API is unreachable or has no
// records for the engagement yet.
// ──────────────────────────────────────────────────────────────────────────────

import type { StatMasterRecord } from "./types/stat-master";

/** Fetch stat-master records for an engagement; null on any failure. */
export async function getStatMasters(
  engagementId: string,
): Promise<StatMasterRecord[] | null> {
  const apiUrl = process.env.CNA_API_INTERNAL_URL;
  if (!apiUrl) return null;

  try {
    const res = await fetch(`${apiUrl}/metrics/${encodeURIComponent(engagementId)}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
    if (!res.ok) return null;
    const data: unknown = await res.json();
    if (!Array.isArray(data) || data.length === 0) return null;
    return data as StatMasterRecord[];
  } catch {
    return null; // API down or timed out — caller derives client-side
  }
}
