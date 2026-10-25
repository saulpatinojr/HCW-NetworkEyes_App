import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  DRAWIO_BASE_PATH,
  DRAWIO_CSP,
  DRAWIO_EMBED_PARAMS,
  DRAWIO_EMBED_SRC,
  DRAWIO_HEADERS,
  DRAWIO_IFRAME_SANDBOX,
  DRAWIO_MESSAGE_ORIGIN,
  isPublicDrawioHost,
  parseDrawioMessage,
} from "@/lib/drawio-embed";
import { createDiagram } from "@/lib/drawio-mcp/server";

// REVIEW.md R-019: the diagram editor must not send customer topology to a public draw.io / diagrams.net host.
// The editor is the draw.io web app served from this deployment under /drawio/. These tests fail if the embed URL
// names a public host, if the CSP lets the editor reach one, if the iframe loses its sandbox, or if any source file
// of the web tier spells such a host out again.

const APP_ROOT = fileURLToPath(new URL("..", import.meta.url));
const THIS_FILE = path.resolve(fileURLToPath(import.meta.url));
const SKIPPED_DIRECTORIES = new Set(["node_modules", ".next", ".git", "coverage", "dist", "drawio"]);
const MAX_FILE_BYTES = 2_000_000;
// A URL, or a bare well-known host such as embed.<domain>, under draw.io's or diagrams.net's domains. The product
// name written as prose ("the draw.io editor") is not a host and does not match.
const PUBLIC_HOST =
  /(?:\/\/|\b(?:embed|viewer|app|www|icons|log|test)\.)(?:[a-z0-9-]+\.)*(?:diagrams\.net|draw\.io)(?![a-z0-9-])/i;

function* walk(directory: string): Generator<string> {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      // public/drawio is the vendored editor (not in git, fetched at image build): it names its own hosts.
      if (!SKIPPED_DIRECTORIES.has(entry.name)) yield* walk(path.join(directory, entry.name));
    } else if (entry.isFile()) {
      yield path.join(directory, entry.name);
    }
  }
}

describe("the diagram editor is served by this deployment", () => {
  it("embeds a relative URL on this origin, not a host", () => {
    expect(DRAWIO_EMBED_SRC.startsWith("/")).toBe(true);
    expect(DRAWIO_EMBED_SRC.startsWith("//")).toBe(false);
    expect(DRAWIO_EMBED_SRC.startsWith(DRAWIO_BASE_PATH)).toBe(true);
    expect(DRAWIO_EMBED_SRC).not.toMatch(/^[a-z][a-z0-9+.-]*:/i);
    expect(isPublicDrawioHost(DRAWIO_EMBED_SRC)).toBe(false);
  });

  it("speaks the proto=json embed protocol with the cloud and logging switches off", () => {
    expect(DRAWIO_EMBED_PARAMS).toMatchObject({ embed: "1", proto: "json", offline: "1", stealth: "1" });
    const query = new URL(DRAWIO_EMBED_SRC, "http://self.invalid").searchParams;
    for (const [key, value] of Object.entries(DRAWIO_EMBED_PARAMS)) expect(query.get(key)).toBe(value);
  });

  it("the MCP create_diagram result points at the same self-hosted editor", () => {
    const result = createDiagram("<mxfile><diagram/></mxfile>", "x");
    expect(result.embedUrl).toBe(DRAWIO_EMBED_SRC);
    expect(isPublicDrawioHost(result.embedUrl)).toBe(false);
  });

  it("sandboxes the iframe without allow-same-origin and messages arrive from the opaque origin", () => {
    const tokens = DRAWIO_IFRAME_SANDBOX.split(/\s+/);
    expect(tokens).toContain("allow-scripts");
    for (const forbidden of ["allow-same-origin", "allow-top-navigation", "allow-popups", "allow-forms"]) {
      expect(tokens).not.toContain(forbidden);
    }
    expect(DRAWIO_MESSAGE_ORIGIN).toBe("null");
  });
});

describe("the editor's Content-Security-Policy", () => {
  const directives = new Map(
    DRAWIO_CSP.split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [name, ...sources] = part.split(/\s+/);
        return [name, sources] as const;
      }),
  );

  it("lets the editor connect to this origin only", () => {
    expect(directives.get("connect-src")).toEqual(["'self'"]);
    expect(directives.get("default-src")).toEqual(["'none'"]);
  });

  it("names no host at all", () => {
    expect(DRAWIO_CSP).not.toMatch(/https?:|\*\.|wss?:/);
    expect(PUBLIC_HOST.test(DRAWIO_CSP)).toBe(false);
  });

  it("allows no inline or eval scripts and no embedding by another site", () => {
    expect(directives.get("script-src")).toEqual(["'self'", "'wasm-unsafe-eval'"]);
    expect(directives.get("frame-ancestors")).toEqual(["'self'"]);
    expect(directives.get("object-src")).toEqual(["'none'"]);
    expect(directives.get("form-action")).toEqual(["'none'"]);
  });

  it("is sent with SAMEORIGIN framing and CORS for the sandboxed frame", () => {
    const headers = Object.fromEntries(DRAWIO_HEADERS.map(({ key, value }) => [key, value]));
    expect(headers["Content-Security-Policy"]).toBe(DRAWIO_CSP);
    expect(headers["X-Frame-Options"]).toBe("SAMEORIGIN");
    expect(headers["Access-Control-Allow-Origin"]).toBe("*");
  });
});

describe("the application's own Content-Security-Policy", () => {
  const middleware = readFileSync(path.join(APP_ROOT, "middleware.ts"), "utf8");

  it("frames only this origin and has the editor's path out of its matcher", () => {
    expect(middleware).toMatch(/frame-src 'self';/);
    expect(PUBLIC_HOST.test(middleware)).toBe(false);
    expect(middleware).toMatch(/matcher:\s*\[[^\]]*\(\?!api\|drawio\//);
  });
});

describe("no source file of the web tier names a public draw.io host", () => {
  it("matches the hosts it must catch and lets this origin through", () => {
    for (const bad of [
      "https://embed.diagrams.net/?embed=1",
      "https://viewer.diagrams.net/",
      "https://app.diagrams.net",
      "http://www.draw.io/x",
      "embed.diagrams.net",
    ]) {
      expect(PUBLIC_HOST.test(bad), bad).toBe(true);
      expect(isPublicDrawioHost(bad), bad).toBe(true);
    }
    for (const good of ["/drawio/index.html?embed=1", "https://example.com/drawio/", "http://localhost:3000/drawio/"]) {
      expect(PUBLIC_HOST.test(good), good).toBe(false);
      expect(isPublicDrawioHost(good), good).toBe(false);
    }
  });

  it("parses messages from the editor defensively", () => {
    expect(parseDrawioMessage('{"event":"init"}')).toEqual({ event: "init", xml: undefined });
    expect(parseDrawioMessage('{"event":"save","xml":"<mxfile/>"}')).toEqual({ event: "save", xml: "<mxfile/>" });
    expect(parseDrawioMessage('{"event":1,"xml":2}')).toEqual({ event: undefined, xml: undefined });
    for (const junk of [null, undefined, 3, {}, "not json", "null", "7", '"s"']) {
      expect(parseDrawioMessage(junk)).toBeNull();
    }
  });

  it("finds no draw.io / diagrams.net host in the files of apps/cna-web", () => {
    const offenders: string[] = [];
    for (const file of walk(APP_ROOT)) {
      if (path.resolve(file) === THIS_FILE) continue;
      if (statSync(file).size > MAX_FILE_BYTES) continue;
      const bytes = readFileSync(file);
      if (bytes.includes(0)) continue;
      const lines = bytes.toString("utf8").split(/\r?\n/);
      lines.forEach((line, index) => {
        if (PUBLIC_HOST.test(line)) offenders.push(`${path.relative(APP_ROOT, file)}:${index + 1}: ${line.trim().slice(0, 100)}`);
      });
    }
    expect(offenders).toEqual([]);
  });
});
