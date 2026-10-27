// Pure href sanitiser for AI-generated Markdown rendered as HTML (SEC-005).
// Deliverable content originates from an LLM fed with untrusted customer input,
// so a link like `[click](javascript:...)` can reach the served document. This
// module is the single testable boundary that neutralises dangerous URL schemes
// while leaving ordinary links, in-page anchors and relative paths intact.

// Only these schemes may appear on a rendered link/image. Everything else
// (javascript:, data:, vbscript:, file:, …) is replaced with a safe no-op.
const SAFE_SCHEMES = new Set(["http", "https", "mailto", "tel"]);

/**
 * Return `href` unchanged when it is safe to render, or `"#"` when it carries a
 * disallowed scheme. Relative URLs and in-page anchors (no scheme) are always
 * safe. The scheme is detected on a copy with control characters and whitespace
 * stripped, so obfuscated schemes such as `java\tscript:` cannot slip past.
 */
export function sanitizeHref(href: unknown): string {
  if (typeof href !== "string") return "#";
  const trimmed = href.trim();
  if (trimmed === "") return "#";

  // Browsers ignore ASCII control chars and whitespace when resolving a URL, so
  // strip them before looking for a scheme to defeat `java\tscript:` style
  // obfuscation. The original string is returned when the scheme is allowed.
  const normalized = trimmed.replace(/[\u0000- \u007F-\u009F]/g, "");

  const schemeMatch = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(normalized);
  if (!schemeMatch) return trimmed; // relative URL or #anchor — safe

  return SAFE_SCHEMES.has(schemeMatch[1].toLowerCase()) ? trimmed : "#";
}

/** Convenience predicate: true when `sanitizeHref` would keep the href. */
export function isSafeHref(href: unknown): boolean {
  return sanitizeHref(href) !== "#" || (typeof href === "string" && href.trim().startsWith("#"));
}

/**
 * Escape a string for use as HTML text or inside a double- or single-quoted
 * attribute value. Covers `"` and `'` as well as `&`, `<`, `>` so a sanitised
 * href or a link title can never terminate the attribute it is placed in.
 */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
