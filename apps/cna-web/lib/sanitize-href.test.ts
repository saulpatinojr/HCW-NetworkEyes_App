import { describe, expect, it } from "vitest";

import { escapeHtml, isSafeHref, sanitizeHref } from "./sanitize-href";

describe("sanitizeHref", () => {
  it("keeps http(s), mailto and tel links", () => {
    expect(sanitizeHref("https://example.com/x?y=1")).toBe("https://example.com/x?y=1");
    expect(sanitizeHref("http://example.com")).toBe("http://example.com");
    expect(sanitizeHref("mailto:ops@cbts.com")).toBe("mailto:ops@cbts.com");
    expect(sanitizeHref("tel:+15135550123")).toBe("tel:+15135550123");
  });

  it("keeps relative URLs and in-page anchors", () => {
    expect(sanitizeHref("/dashboard")).toBe("/dashboard");
    expect(sanitizeHref("./report.html")).toBe("./report.html");
    expect(sanitizeHref("../up")).toBe("../up");
    expect(sanitizeHref("#section-2")).toBe("#section-2");
    expect(sanitizeHref("report?tab=1")).toBe("report?tab=1");
  });

  it("blocks javascript: URLs", () => {
    expect(sanitizeHref("javascript:alert(document.cookie)")).toBe("#");
    expect(sanitizeHref("JavaScript:alert(1)")).toBe("#");
    expect(sanitizeHref("  javascript:alert(1)  ")).toBe("#");
  });

  it("blocks data: and vbscript: and file: URLs", () => {
    expect(sanitizeHref("data:text/html,<script>alert(1)</script>")).toBe("#");
    expect(sanitizeHref("data:image/png;base64,AAAA")).toBe("#");
    expect(sanitizeHref("vbscript:msgbox(1)")).toBe("#");
    expect(sanitizeHref("file:///etc/passwd")).toBe("#");
  });

  it("blocks schemes obfuscated with control characters or whitespace", () => {
    expect(sanitizeHref("java\tscript:alert(1)")).toBe("#");
    expect(sanitizeHref("java\nscript:alert(1)")).toBe("#");
    expect(sanitizeHref("java script:alert(1)")).toBe("#");
    expect(sanitizeHref("\u0000javascript:alert(1)")).toBe("#");
  });

  it("handles non-string and empty input safely", () => {
    expect(sanitizeHref(null)).toBe("#");
    expect(sanitizeHref(undefined)).toBe("#");
    expect(sanitizeHref(123)).toBe("#");
    expect(sanitizeHref("")).toBe("#");
    expect(sanitizeHref("   ")).toBe("#");
  });

  it("isSafeHref agrees with sanitizeHref", () => {
    expect(isSafeHref("https://example.com")).toBe(true);
    expect(isSafeHref("#top")).toBe(true);
    expect(isSafeHref("/path")).toBe(true);
    expect(isSafeHref("javascript:alert(1)")).toBe(false);
    expect(isSafeHref("data:text/html,x")).toBe(false);
  });
});

describe("escapeHtml", () => {
  it("escapes quotes so a value cannot break out of an attribute", () => {
    expect(escapeHtml('https://ok.example"onmouseover="alert(1)')).toBe(
      "https://ok.example&quot;onmouseover=&quot;alert(1)",
    );
    expect(escapeHtml("a' onmouseover='x")).toBe("a&#39; onmouseover=&#39;x");
    expect(escapeHtml("<b>&</b>")).toBe("&lt;b&gt;&amp;&lt;/b&gt;");
  });
});
