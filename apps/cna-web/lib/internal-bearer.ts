// Check for the internal shared bearer on a web route that only the Python
// engine calls (ticket #245, owner decision "internal-only").
//
// It reuses the one shared secret the tiers already use, `CNA_API_TOKEN` (see
// `api-client.ts` for the web→api direction; `apps/cna-api/auth.py` for the api
// side). The check fails closed: when the token is not configured on this
// container nothing can match, so every request is refused. The token is never
// logged and never echoed.

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

// A random key, new for every process, so the digests below mean nothing outside this process.
// The token is a high-entropy shared secret, not a user password, and nothing here is stored:
// the keyed digest only makes both sides the same length for `timingSafeEqual`. (A plain SHA-256
// of the token also works, but static analysis rightly reads "token hashed with a fast hash" as
// password storage, CodeQL js/insufficient-password-hash.)
const COMPARE_KEY = randomBytes(32);

function digest(value: string): Buffer {
  return createHmac("sha256", COMPARE_KEY).update(value, "utf8").digest();
}

/**
 * True when the request carries `Authorization: Bearer <CNA_API_TOKEN>`.
 * Both sides are digested first so the comparison takes the same time whatever
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
