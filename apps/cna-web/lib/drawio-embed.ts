// The diagram editor is the draw.io web app, served by this deployment from /drawio/ (see the `drawio-webapp` stage
// of apps/cna-web/Dockerfile). No topology leaves the deployment: the editor is loaded from this origin, and the
// Content-Security-Policy below lets it talk to nothing else. REVIEW.md R-019 records the decision.
//
// This module is plain TypeScript with no framework imports so that next.config.ts, the middleware matcher, the
// editor component, the MCP route and the tests all read the same values.

/** Where the self-hosted editor is served. A path on this origin, never a host. */
export const DRAWIO_BASE_PATH = "/drawio/";

/**
 * Parameters of the embed. `embed=1&proto=json` is the postMessage protocol the host page speaks
 * (DrawioEmbed.tsx). `offline=1` turns off the cloud-storage integrations and `stealth=1` turns off the editor's
 * own logging; both are belt and braces, because the CSP below already refuses every request to another host.
 */
export const DRAWIO_EMBED_PARAMS: Readonly<Record<string, string>> = {
  embed: "1",
  ui: "min",
  spin: "1",
  proto: "json",
  libraries: "1",
  noExitBtn: "1",
  offline: "1",
  stealth: "1",
};

/** The iframe `src`: a same-origin relative URL. */
export const DRAWIO_EMBED_SRC = `${DRAWIO_BASE_PATH}index.html?${new URLSearchParams(DRAWIO_EMBED_PARAMS).toString()}`;

/**
 * The iframe is sandboxed WITHOUT `allow-same-origin`: the editor gets an opaque origin, so its scripts cannot read
 * this application's cookies, storage or same-origin responses even though they are served from the same host.
 * That is why the files under /drawio/ carry `Access-Control-Allow-Origin: *` (see `DRAWIO_HEADERS`): the editor
 * fetches its own language file with XHR, and an opaque origin needs CORS for that. The files are public static
 * assets of an Apache-2.0 project and hold no customer data, so nothing is exposed by it. (A browser that applies
 * Private Network Access lets any site read them from an appliance on a private address; that is public code.)
 *
 * The same flags are also sent as the `sandbox` directive of the editor's own CSP (`DRAWIO_CSP`), so the sandbox
 * holds when someone opens /drawio/index.html directly instead of through this iframe.
 */
export const DRAWIO_IFRAME_SANDBOX = "allow-scripts allow-modals allow-downloads";

/** Messages from a sandboxed frame arrive with the origin string "null". */
export const DRAWIO_MESSAGE_ORIGIN = "null";

/**
 * Content-Security-Policy of the editor's own files. `connect-src 'self'` is the control that matters: whatever the
 * editor's code or a hostile diagram tried, the browser refuses a request to any other host. The editor needs
 * 'wasm-unsafe-eval' for its connector-routing module and `blob:` for exports; it needs no inline script.
 *
 * `sandbox` makes the editor's document an opaque origin however it is opened. Without it, a direct visit to
 * /drawio/index.html would run the editor with this application's origin: it could read the session cookie that is
 * not HttpOnly and its same-origin requests would carry the session.
 */
export const DRAWIO_CSP = [
  "default-src 'none'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
  "frame-ancestors 'self'",
  `sandbox ${DRAWIO_IFRAME_SANDBOX}`,
].join("; ");

/** Response headers for /drawio/:path* (next.config.ts). */
export const DRAWIO_HEADERS: ReadonlyArray<{ key: string; value: string }> = [
  { key: "Content-Security-Policy", value: DRAWIO_CSP },
  // The app-wide X-Frame-Options is DENY, which would also block this same-origin iframe.
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Access-Control-Allow-Origin", value: "*" },
];

/** What the editor posts to the host page; only the fields the host reads. */
export type DrawioMessage = { event?: string; xml?: string };

/** Parses a message the editor posted. Anything that is not a JSON object yields null. */
export function parseDrawioMessage(data: unknown): DrawioMessage | null {
  if (typeof data !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (typeof parsed !== "object" || parsed === null) return null;
    const { event, xml } = parsed as Record<string, unknown>;
    return {
      event: typeof event === "string" ? event : undefined,
      xml: typeof xml === "string" ? xml : undefined,
    };
  } catch {
    return null;
  }
}

/** True when `url` names a host run by draw.io / diagrams.net rather than this deployment. */
export function isPublicDrawioHost(url: string): boolean {
  // The text up to the first "/", "?", "#" or ":" once a scheme is dropped. A path such as "/drawio/index.html" has
  // no host; a bare "embed.<domain>" is one.
  const host = (url.trim().replace(/^[a-z][a-z0-9+.-]*:\/\//i, "").replace(/^\/\//, "").split(/[/?#:]/)[0] ?? "").toLowerCase();
  return /(^|\.)(diagrams\.net|draw\.io|drawio\.com)$/.test(host);
}

/** Where a reply to the editor goes: an opaque origin accepts no other target origin. See DrawioEmbed.tsx. */
export const DRAWIO_REPLY_TARGET = "*";

/** The one method of the editor's window the host page uses. */
export type DrawioFrameWindow = { postMessage(message: string, targetOrigin: string): void };

/**
 * Handles one `message` event for the editor iframe. Pure of the DOM so that it can be tested with fake windows.
 *
 * - A message from any window other than the iframe's own is ignored, and so is one whose origin is not the
 *   sandbox's opaque "null".
 * - `init` is answered with `load` carrying the diagram; `save` is forwarded to `onSave` and answered with `status`.
 * - Replies go to `frameWindow` only.
 */
export function handleDrawioMessage(
  event: { source: unknown; origin: string; data: unknown },
  frameWindow: DrawioFrameWindow | null | undefined,
  initialXml: string,
  onSave?: (xml: string) => void,
): void {
  if (!frameWindow || event.source !== frameWindow) return;
  if (event.origin !== DRAWIO_MESSAGE_ORIGIN) return;

  const msg = parseDrawioMessage(event.data);
  if (msg?.event === "init") {
    frameWindow.postMessage(JSON.stringify({ action: "load", xml: initialXml, autosave: 0 }), DRAWIO_REPLY_TARGET);
  } else if (msg?.event === "save" && typeof msg.xml === "string") {
    onSave?.(msg.xml);
    frameWindow.postMessage(
      JSON.stringify({ action: "status", message: "Saved to engagement", modified: false }),
      DRAWIO_REPLY_TARGET,
    );
  }
}
