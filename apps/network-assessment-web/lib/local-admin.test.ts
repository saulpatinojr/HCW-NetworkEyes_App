import { describe, expect, it } from "vitest";

import { hashLocalAdminPassword, verifyLocalAdminPassword } from "./local-admin";

describe("local-admin password hashing (PBKDF2-HMAC-SHA256)", () => {
  it("produces the pbkdf2$sha256$<iter>$<salt>$<hash> format", () => {
    const hash = hashLocalAdminPassword("correct horse battery staple");
    const parts = hash.split("$");
    expect(parts).toHaveLength(5);
    expect(parts[0]).toBe("pbkdf2");
    expect(parts[1]).toBe("sha256");
    expect(Number(parts[2])).toBeGreaterThan(0);
  });

  it("salts each hash (same password → different stored hash)", () => {
    const a = hashLocalAdminPassword("pw");
    const b = hashLocalAdminPassword("pw");
    expect(a).not.toBe(b);
  });

  it("verifies a correct password", () => {
    const hash = hashLocalAdminPassword("s3cur3-pass");
    expect(verifyLocalAdminPassword("s3cur3-pass", hash)).toBe(true);
  });

  it("rejects a wrong password", () => {
    const hash = hashLocalAdminPassword("s3cur3-pass");
    expect(verifyLocalAdminPassword("wrong-pass", hash)).toBe(false);
  });

  it("rejects a malformed hash without throwing", () => {
    expect(verifyLocalAdminPassword("pw", "")).toBe(false);
    expect(verifyLocalAdminPassword("pw", "not-a-hash")).toBe(false);
    expect(verifyLocalAdminPassword("pw", "pbkdf2$sha256$210000$onlyfourparts")).toBe(false);
    // Wrong algorithm prefix.
    expect(verifyLocalAdminPassword("pw", "bcrypt$sha256$210000$c2FsdA==$aGFzaA==")).toBe(false);
    // Non-numeric iteration count.
    expect(verifyLocalAdminPassword("pw", "pbkdf2$sha256$abc$c2FsdA==$aGFzaA==")).toBe(false);
  });

  it("verifies a fixed known-answer vector (format contract for any hash producer)", () => {
    // Independent derivation: PBKDF2-HMAC-SHA256, 210000 iterations, 32-byte key,
    // salt = bytes 0x00..0x0f, password "known-answer-password". Any tool that creates a
    // LOCAL_ADMIN_PASSWORD value must reproduce this exact string for these inputs.
    const KNOWN_ANSWER = {
      plain: "known-answer-password",
      stored: "pbkdf2$sha256$210000$AAECAwQFBgcICQoLDA0ODw==$b5qGipp/z4tLnP3UFGC2VRtlJulSmgP/16509H82Y20=",
    };
    expect(verifyLocalAdminPassword(KNOWN_ANSWER.plain, KNOWN_ANSWER.stored)).toBe(true);
    expect(verifyLocalAdminPassword(KNOWN_ANSWER.plain + "x", KNOWN_ANSWER.stored)).toBe(false);
    const parts = KNOWN_ANSWER.stored.split("$");
    expect(parts.slice(0, 3)).toEqual(["pbkdf2", "sha256", "210000"]);
    expect(Buffer.from(parts[3], "base64")).toHaveLength(16);
    expect(Buffer.from(parts[4], "base64")).toHaveLength(32);
  });

  it("interoperates across independent hash+verify cycles", () => {
    for (const pw of ["", "short", "a very long passphrase with spaces and 123!@#"]) {
      const hash = hashLocalAdminPassword(pw);
      expect(verifyLocalAdminPassword(pw, hash)).toBe(true);
      expect(verifyLocalAdminPassword(pw + "x", hash)).toBe(false);
    }
  });
});
