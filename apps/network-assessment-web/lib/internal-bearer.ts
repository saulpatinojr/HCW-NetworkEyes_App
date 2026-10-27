// Check for the internal shared bearer on a web route that only the Python
// engine calls (ticket #245, owner decision "internal-only").
//
// It reuses the one shared secret the tiers already use, `CNA_API_TOKEN` (see
// `api-client.ts` for the web→api direction; `apps/network-assessment-api/auth.py` for the api
// side). The check fails closed: when the token is not configured on this
// container nothing can match, so every request is refused. The token is never
// logged and never echoed.

import { timingSafeEqual } from "node:crypto";

// Constant-time equality of two strings. Both are copied into zero-filled buffers of the longer length so
// `timingSafeEqual` (which needs equal lengths) can compare every byte whatever the lengths are; the lengths
// themselves are compared last. No hash is involved: the token is a shared secret that is compared, never
// stored, and hashing it (even with a key) is what CodeQL reads as password hashing
// (js/insufficient-password-hash, alert 1).
function sameSecret(provided: string, expected: string): boolean {
  const a = Buffer.from(provided, "utf8");
  const b = Buffer.from(expected, "utf8");
  const length = Math.max(a.length, b.length, 1);
  const paddedA = Buffer.alloc(length);
  const paddedB = Buffer.alloc(length);
  a.copy(paddedA);
  b.copy(paddedB);
  return timingSafeEqual(paddedA, paddedB) && a.length === b.length;
}

/**
 * True when the request carries `Authorization: Bearer <CNA_API_TOKEN>`.
 * The comparison takes the same time for every wrong value of the same length and does not stop at the
 * first differing byte.
 */
export function hasValidInternalBearer(req: Request): boolean {
  const expected = process.env.CNA_API_TOKEN;
  if (!expected) return false;

  const header = req.headers.get("authorization") ?? "";
  const space = header.indexOf(" ");
  if (space < 0 || header.slice(0, space).toLowerCase() !== "bearer") return false;

  return sameSecret(header.slice(space + 1), expected);
}
