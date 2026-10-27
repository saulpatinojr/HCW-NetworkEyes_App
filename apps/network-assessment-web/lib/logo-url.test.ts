import { describe, expect, it } from "vitest";

import { ALLOWED_LOGO_HOSTS, validateLogoUrl } from "./logo-url";

// The logo host allow-list guards against steering the application to an attacker's host (OWA-07). The company
// hosts it once carried are gone (issue #318: the owner chose the Hybrid Cloud Works logo), and the built-in logo is a
// path on this site, so the list needs no host for it.
const REJECTED = { error: "Logo URL must be hosted on an approved CDN." };

describe("validateLogoUrl", () => {
  it("keeps exactly the two cloud-storage hosts and no company host", () => {
    expect([...ALLOWED_LOGO_HOSTS]).toEqual(["storage.azure.com", "githubusercontent.com"]);
    for (const host of ALLOWED_LOGO_HOSTS) expect(host).not.toMatch(/cbts/i);
  });

  it("accepts an empty value and the built-in Hybrid Cloud Works logo paths without any host", () => {
    for (const value of [null, "", "   ", "/hcw-logo-black.png", "/hcw-logo-white.png"]) {
      expect(validateLogoUrl(value), String(value)).toBeNull();
    }
  });

  it("accepts the two allowed hosts and their subdomains", () => {
    for (const value of [
      "https://raw.githubusercontent.com/example/repo/main/logo.png",
      "https://githubusercontent.com/logo.png",
      "https://account.storage.azure.com/logo.png",
    ]) {
      expect(validateLogoUrl(value), value).toBeNull();
    }
  });

  it("rejects the company hosts the list once carried", () => {
    for (const value of ["https://cdn.cbts.com/logo.png", "https://cbts.com/logo.png", "https://www.cbts.com/x.png"]) {
      expect(validateLogoUrl(value), value).toEqual(REJECTED);
    }
  });

  it("rejects any other host, including look-alikes of an allowed host", () => {
    for (const value of [
      "https://evil.example/logo.png",
      "https://githubusercontent.com.evil.example/logo.png",
      "https://evilgithubusercontent.com/logo.png",
      "http://169.254.169.254/latest/meta-data/",
      "https://localhost/logo.png",
    ]) {
      expect(validateLogoUrl(value), value).toEqual(REJECTED);
    }
  });

  it("does not treat a protocol-relative, backslash or control-character address as a path on this site", () => {
    // "//evil.example/x.png" starts with "/", but a browser or a server-side fetch reads it as another host. So does
    // "/<tab>/evil.example/x.png": URL parsers delete tab, line feed and carriage return before they read it.
    for (const value of [
      "//evil.example/logo.png",
      "/\\evil.example/logo.png",
      "\\\\evil.example/logo.png",
      "/\t/evil.example/logo.png",
      "/\n/evil.example/logo.png",
      "/\r/evil.example/logo.png",
      "/\t\\evil.example/logo.png",
      "/\\\t/evil.example/logo.png",
      "/logo.png\n//evil.example",
      "/logo\u0000.png",
    ]) {
      expect(validateLogoUrl(value), JSON.stringify(value)).toEqual({ error: "Invalid logo URL format." });
    }
  });

  it("still accepts a plain site path with a query or a fragment", () => {
    for (const value of ["/hcw-logo-black.png?v=2", "/img/logo.png#top", "/a/b-c_d.e/logo.png"]) {
      expect(validateLogoUrl(value), value).toBeNull();
    }
  });

  it("rejects a URL with no host and text that is not a URL", () => {
    // A data: URL has no host, so it is rejected too: the upload form sends one (an existing behaviour, not changed here).
    expect(validateLogoUrl("data:image/png;base64,AAAA")).toEqual(REJECTED);
    expect(validateLogoUrl("javascript:alert(1)")).toEqual(REJECTED);
    expect(validateLogoUrl("not a url")).toEqual({ error: "Invalid logo URL format." });
  });
});
