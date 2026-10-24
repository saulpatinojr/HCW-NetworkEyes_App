// Check for the internal shared bearer on a web route that only the Python
// engine calls (ticket #245, owner decision "internal-only").
//
// It reuses the one shared secret the tiers already use, `CNA_API_TOKEN` (see
// `api-client.ts` for the web→api direction; `apps/cna-api/auth.py` for the api
// side). The check fails closed: when the token is not configured on this
// container nothing can match, so every request is refused. The token is never
// logged and never echoed.

import { createHash, timingSafeEqual } from "node:crypto";

function digest(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest();
}

/**
 * True when the request carries `Authorization: Bearer <CNA_API_TOKEN>`.
 * Both sides are hashed first so the comparison takes the same time whatever
 * the lengths are, then compared with `timingSafeEqual`.
 */
export function hasValidInternalBearer(req: Request): boolean {
  const expected = process.env.CNA_API_TOKEN;
  if (!expected) return false;

  const header = req.headers.get("authorization") ?? "";
  const space = header.indexOf(" ");
  if (space < 0 || header.slice(0, space).toLowerCase() !== "bearer") return false;

  return timingSafeEqual(digest(header.slice(space + 1)), digest(expected));
}
