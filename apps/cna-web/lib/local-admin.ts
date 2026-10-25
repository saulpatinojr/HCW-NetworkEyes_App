import { pbkdf2Sync, randomBytes, timingSafeEqual } from "crypto";

// Break-glass local admin password hashing. PBKDF2-HMAC-SHA256 via Node's
// built-in crypto — no bcrypt/argon2 dependency needed.
//
// Stored format (any tool that produces a hash, e.g. one built on
// System.Security.Cryptography.Rfc2898DeriveBytes, must emit exactly this):
//   pbkdf2$sha256$210000$<salt b64>$<hash b64>
// i.e. the literal "pbkdf2" and "sha256", the iteration count, the random salt
// and the 32-byte derived key, both standard Base64, joined with "$". A fixed
// known-answer vector in local-admin.test.ts lets any producer self-check.
const ALGO = "pbkdf2";
const DIGEST = "sha256";
const ITERATIONS = 210_000; // OWASP 2023 minimum for PBKDF2-HMAC-SHA256
const KEY_LENGTH = 32;

/**
 * Hash a plaintext password into the stored format:
 * "pbkdf2$sha256$210000$<saltBase64>$<hashBase64>"
 */
export function hashLocalAdminPassword(plaintext: string): string {
  const salt = randomBytes(16);
  const derivedKey = pbkdf2Sync(plaintext, salt, ITERATIONS, KEY_LENGTH, DIGEST);
  return [ALGO, DIGEST, ITERATIONS, salt.toString("base64"), derivedKey.toString("base64")].join("$");
}

/**
 * Verify a plaintext password against a hash in the stored format above
 * (produced by hashLocalAdminPassword or by any other producer of that format).
 * Uses a constant-time comparison — never compare derived keys with `===`.
 */
export function verifyLocalAdminPassword(plaintext: string, storedHash: string): boolean {
  const parts = storedHash.split("$");
  if (parts.length !== 5 || parts[0] !== ALGO) return false;

  const [, digest, iterationsRaw, saltB64, hashB64] = parts;
  const iterations = Number.parseInt(iterationsRaw, 10);
  if (!Number.isFinite(iterations) || iterations <= 0) return false;

  const salt = Buffer.from(saltB64, "base64");
  const expected = Buffer.from(hashB64, "base64");
  const actual = pbkdf2Sync(plaintext, salt, iterations, expected.length, digest);

  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
