// OWA-07: SSRF defense for the optional report logo.
//
// The report's logo is either the built-in Hybrid Cloud Works logo (a path on this site, /hcw-logo-black.png and
// /hcw-logo-white.png in public/) or a URL the person supplies. A path on this site needs no host check, so the
// built-in logo needs nothing on the list below. Any other URL must be on one of these hosts (or a subdomain of one).
// Today the value is checked and then not read by anything (it is copied into the report context and ends there), so
// this list is the guard for the day something fetches or shows it. Keep it as short as it can be: every host here is
// a server this application could then be steered into reading. Before using the value, also require https, no
// user name or port, and a length limit, and store the parsed address, not the text that was typed.
export const ALLOWED_LOGO_HOSTS = ["storage.azure.com", "githubusercontent.com"] as const;

// One slash, then anything except a second slash, a backslash or a control character (tab, line feed, carriage
// return, NUL ...). URL parsers delete tab, line feed and carriage return before they read an address, so
// "/<tab>/host/x" and a backslash after the slash are read as another host; testing the first two characters would
// miss them.
const SITE_PATH = /^\/(?![/\\])[^\u0000-\u001f\u007f\\]*$/;

/** A path on this site, such as /hcw-logo-black.png. */
function isSitePath(url: string): boolean {
  return SITE_PATH.test(url);
}

/** Returns `null` when the logo URL is acceptable (or empty), otherwise an error message for the person. */
export function validateLogoUrl(url: string | null): { error?: string } | null {
  if (!url || url.trim() === "") return null;
  try {
    if (!isSitePath(url)) {
      const parsed = new URL(url);
      const isAllowed = ALLOWED_LOGO_HOSTS.some(
        (host) => parsed.hostname === host || parsed.hostname.endsWith("." + host),
      );
      if (!isAllowed) {
        return { error: "Logo URL must be hosted on an approved CDN." };
      }
    }
    return null;
  } catch {
    return { error: "Invalid logo URL format." };
  }
}
