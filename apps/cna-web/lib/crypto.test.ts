import { randomBytes } from "crypto";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { decrypt, encrypt } from "./crypto";

describe("crypto (AES-256-GCM)", () => {
  const original = process.env.CREDENTIAL_ENCRYPTION_KEY;

  beforeAll(() => {
    // 32-byte key, base64 — a throwaway test key, never a real secret.
    process.env.CREDENTIAL_ENCRYPTION_KEY = randomBytes(32).toString("base64");
  });
  afterAll(() => {
    if (original === undefined) delete process.env.CREDENTIAL_ENCRYPTION_KEY;
    else process.env.CREDENTIAL_ENCRYPTION_KEY = original;
  });

  it("round-trips plaintext", () => {
    const plaintext = "sp-client-value-«ünïçøde»-123";
    const ct = encrypt(plaintext);
    expect(ct).not.toContain(plaintext);
    expect(decrypt(ct)).toBe(plaintext);
  });

  it("produces a unique IV per call (ciphertext differs for same input)", () => {
    const a = encrypt("same");
    const b = encrypt("same");
    expect(a).not.toBe(b);
    expect(decrypt(a)).toBe("same");
    expect(decrypt(b)).toBe("same");
  });

  it("uses the iv:tag:ciphertext base64 format", () => {
    const parts = encrypt("x").split(":");
    expect(parts).toHaveLength(3);
    parts.forEach((p) => expect(p).toMatch(/^[A-Za-z0-9+/]+=*$/));
  });

  it("rejects a tampered ciphertext (GCM auth tag mismatch)", () => {
    const ct = encrypt("tamper-me");
    const [iv, tag, data] = ct.split(":");
    // Flip a byte in the ciphertext segment.
    const buf = Buffer.from(data, "base64");
    buf[0] = buf[0] ^ 0xff;
    const tampered = [iv, tag, buf.toString("base64")].join(":");
    expect(() => decrypt(tampered)).toThrow();
  });

  it("rejects a tampered auth tag", () => {
    const ct = encrypt("tamper-tag");
    const [iv, tag, data] = ct.split(":");
    const buf = Buffer.from(tag, "base64");
    buf[0] = buf[0] ^ 0xff;
    expect(() => decrypt([iv, buf.toString("base64"), data].join(":"))).toThrow();
  });

  it("rejects a malformed ciphertext string", () => {
    expect(() => decrypt("not-a-valid-format")).toThrow("Invalid ciphertext format");
  });
});
