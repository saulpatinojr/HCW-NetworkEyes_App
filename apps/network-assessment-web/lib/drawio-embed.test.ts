import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import nextConfig from "@/next.config";
import { config as middlewareConfig } from "@/middleware";
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
// names a public host, if the CSP lets the editor reach one or loses its sandbox, if the iframe loses its sandbox,
// if next.config.ts stops sending the editor's headers, or if any source file of the web tier spells such a host out
// again. The editor's own files (public/drawio, fetched at image build) are the one thing the scan does not read.

const APP_ROOT = fileURLToPath(new URL("..", import.meta.url));
const THIS_FILE = path.resolve(fileURLToPath(import.meta.url));
const SKIPPED_DIRECTORIES = new Set(["node_modules", ".next", ".git", "coverage", "dist"]);
// The vendored editor names its own hosts (it is third-party code); it is skipped at this exact path and nowhere else.
const VENDORED_EDITOR = path.join(APP_ROOT, "public", "drawio");
const MAX_FILE_BYTES = 2_000_000;
// A URL, or a bare well-known host such as embed.<domain>, under draw.io's, diagrams.net's or drawio.com's domains.
// The product name written as prose ("the draw.io editor") is not a host and does not match.
const PUBLIC_HOST =
  /(?:\/\/|\b(?:embed|viewer|app|www|icons|log|test)\.)(?:[a-z0-9-]+\.)*(?:diagrams\.net|draw\.io|drawio\.com)(?![a-z0-9-])/i;

function* walk(directory: string): Generator<string> {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!SKIPPED_DIRECTORIES.has(entry.name) && path.resolve(full) !== VENDORED_EDITOR) yield* walk(full);
    } else if (entry.isFile()) {
      yield full;
    }
  }
}

function parseCsp(csp: string): Map<string, string[]> {
  return new Map(
    csp
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const [name, ...sources] = part.split(/\s+/);
        return [name, sources] as const;
      }),
  );
}

// A CSP source this policy may contain: a quoted keyword, a data:/blob: scheme, or (in `sandbox`) an allow-* flag.
// A bare `*`, a bare host, a scheme such as https: and a URL are all refused.
const ALLOWED_SOURCE_SHAPE = /^(?:'[a-z-]+'|(?:data|blob):|allow-[a-z-]+)$/;

function looseSources(csp: string): string[] {
  const loose: string[] = [];
  for (const [name, sources] of parseCsp(csp)) {
    for (const source of sources) if (!ALLOWED_SOURCE_SHAPE.test(source)) loose.push(`${name} ${source}`);
  }
  return loose;
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
  // Every directive, with exactly the sources it may have. Adding a source is a reviewed change to this table.
  const EXPECTED: Record<string, string[]> = {
    "default-src": ["'none'"],
    "script-src": ["'self'", "'wasm-unsafe-eval'"],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'", "data:"],
    "connect-src": ["'self'"],
    "worker-src": ["'self'", "blob:"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'none'"],
    "frame-ancestors": ["'self'"],
    sandbox: ["allow-scripts", "allow-modals", "allow-downloads"],
  };
  const directives = parseCsp(DRAWIO_CSP);

  it("has exactly the expected directives, each with exactly its expected sources", () => {
    expect([...directives.keys()].sort()).toEqual(Object.keys(EXPECTED).sort());
    for (const [name, sources] of Object.entries(EXPECTED)) expect(directives.get(name), name).toEqual(sources);
  });

  it("carries the same sandbox flags as the iframe, so a direct visit is sandboxed too", () => {
    expect(directives.get("sandbox")).toEqual(DRAWIO_IFRAME_SANDBOX.split(/\s+/));
    expect(directives.get("sandbox")).not.toContain("allow-same-origin");
  });

  it("names no host, no bare *, no scheme other than data: and blob:", () => {
    expect(looseSources(DRAWIO_CSP)).toEqual([]);
    expect(PUBLIC_HOST.test(DRAWIO_CSP)).toBe(false);
  });

  it("the looseness check catches what it must", () => {
    for (const bad of [
      "connect-src 'self' *",
      "img-src 'self' example.com",
      "img-src *",
      "connect-src 'self' https://example.com",
      "connect-src 'self' wss://example.com",
      "script-src 'self' *.example.com",
      "font-src https:",
      "sandbox allow-scripts allow-same-origin x.y",
    ]) {
      expect(looseSources(bad), bad).not.toEqual([]);
    }
    expect(looseSources("img-src 'self' data: blob:; sandbox allow-scripts")).toEqual([]);
  });

  it("is sent with SAMEORIGIN framing and CORS for the sandboxed frame", () => {
    const headers = Object.fromEntries(DRAWIO_HEADERS.map(({ key, value }) => [key, value]));
    expect(headers["Content-Security-Policy"]).toBe(DRAWIO_CSP);
    expect(headers["X-Frame-Options"]).toBe("SAMEORIGIN");
    expect(headers["Access-Control-Allow-Origin"]).toBe("*");
  });
});

describe("next.config.ts and the middleware", () => {
  it("send the editor's headers on /drawio/:path*, after the app-wide rule they override", async () => {
    const rules = (await nextConfig.headers?.()) ?? [];
    const sources = rules.map((rule) => rule.source);
    const index = sources.indexOf(`${DRAWIO_BASE_PATH}:path*`);
    expect(index, `sources: ${sources.join(", ")}`).toBeGreaterThan(sources.indexOf("/(.*)"));
    expect(sources.indexOf("/(.*)")).toBeGreaterThanOrEqual(0);
    expect(rules[index].headers).toEqual(DRAWIO_HEADERS);
  });

  it("the app-wide rule still denies framing (the editor rule is the only exception for this path)", async () => {
    const rules = (await nextConfig.headers?.()) ?? [];
    const all = rules.find((rule) => rule.source === "/(.*)");
    expect(all?.headers).toContainEqual({ key: "X-Frame-Options", value: "DENY" });
  });

  it("the application CSP frames only this origin", () => {
    const middleware = readFileSync(path.join(APP_ROOT, "middleware.ts"), "utf8");
    expect(middleware).toMatch(/frame-src 'self';/);
    expect(PUBLIC_HOST.test(middleware)).toBe(false);
  });

  it("the middleware matcher leaves /drawio/ out and keeps every other page in", () => {
    const [matcher] = middlewareConfig.matcher;
    const pattern = new RegExp(`^${matcher}$`);
    for (const out of ["/drawio/index.html", "/drawio/js/app.min.js", "/api/health", "/_next/static/x.js"]) {
      expect(pattern.test(out), out).toBe(false);
    }
    for (const kept of ["/", "/dashboard", "/engagements/1/diagram", "/auth/signin", "/drawio", "/drawio-notes"]) {
      expect(pattern.test(kept), kept).toBe(true);
    }
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
      "https://www.drawio.com/doc/faq",
      "//app.drawio.com/",
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

  it("scans the sources, tests and configuration, and skips only the vendored editor", () => {
    const files = [...walk(APP_ROOT)].map((file) => path.relative(APP_ROOT, file).replaceAll("\\", "/"));
    for (const expected of [
      "middleware.ts",
      "next.config.ts",
      "lib/drawio-embed.ts",
      "lib/drawio-embed.test.ts",
      "components/diagrams/DrawioEmbed.tsx",
      "components/diagrams/DrawioEmbed.test.tsx",
      "app/api/drawio-mcp/[...path]/route.ts",
      "lib/drawio-mcp/server.ts",
      "Dockerfile",
    ]) {
      expect(files, expected).toContain(expected);
    }
    expect(files.some((file) => file.startsWith("public/drawio/"))).toBe(false);
  });

  it("finds no draw.io / diagrams.net / drawio.com host in the files of apps/network-assessment-web", () => {
    const offenders: string[] = [];
    for (const file of walk(APP_ROOT)) {
      if (path.resolve(file) === THIS_FILE) continue;
      if (statSync(file).size > MAX_FILE_BYTES) continue;
      const bytes = readFileSync(file);
      if (bytes.includes(0)) continue;
      const lines = bytes.toString("utf8").split(/\r?\n/);
      lines.forEach((line, index) => {
        if (PUBLIC_HOST.test(line)) {
          offenders.push(`${path.relative(APP_ROOT, file)}:${index + 1}: ${line.trim().slice(0, 100)}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });
});
