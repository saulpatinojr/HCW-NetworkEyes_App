import { readFileSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

// TypeScript 7 ships a native compiler with no programmatic API (7.1 brings a new, different one), and
// typescript-eslint refuses to load against it. The supported way to run both is side by side
// (https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/):
//
//   "typescript":         "npm:@typescript/typescript6@^6.0.2"   the TypeScript 6 API that eslint and Next.js import
//   "@typescript/native": "npm:typescript@^7.0.2"                 supplies the `tsc` used by `npm run typecheck`
//
// A bump that breaks this pairing used to surface as a crash inside `npm run lint` (Dependabot #209). These tests
// fail first, with the fix written in the message. Dependabot does not track either alias (it only lists direct,
// non-aliased dependencies), so no ignore rule is needed for them; this file is the guard instead.
//
// The last test is the exit: it fails as soon as the installed typescript-eslint admits a TypeScript 7.1 or later
// peer, which is the moment the TypeScript 6 compatibility package can go (TODO.md T-731).

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const devDependencies: Record<string, string> = pkg.devDependencies;

function installedVersion(name: string): string {
  const file = new URL(`../node_modules/${name}/package.json`, import.meta.url);
  return JSON.parse(readFileSync(file, "utf8")).version;
}

type Version = [number, number, number];

function parseVersion(text: string): Version {
  const [major = "0", minor = "0", patch = "0"] = text.split(".");
  return [Number(major), Number(minor), Number.parseInt(patch, 10) || 0];
}

function compare(a: Version, b: Version): number {
  return a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
}

/** True when a peer range such as ">=4.8.4 <6.1.0" has no upper bound or one above `version`. */
function rangeReaches(range: string, version: Version): boolean {
  const bounds = [...range.matchAll(/(<=?)\s*(\d+(?:\.\d+){0,2})/g)];
  if (bounds.length === 0) return true;
  return bounds.every(([, operator, bound]) => {
    const order = compare(parseVersion(bound), version);
    return operator === "<=" ? order >= 0 : order > 0;
  });
}

describe("TypeScript 6 API and TypeScript 7 compiler side by side", () => {
  it("keeps `typescript` as the TypeScript 6 compatibility package", () => {
    expect(
      devDependencies.typescript,
      'package.json "typescript" must stay "npm:@typescript/typescript6@^6.0.2"; a plain typescript@7 breaks typescript-eslint',
    ).toMatch(/^npm:@typescript\/typescript6@/);
    expect(installedVersion("typescript")).toMatch(/^6\./);
  });

  it("type-checks with the TypeScript 7 compiler", () => {
    expect(
      devDependencies["@typescript/native"],
      'package.json "@typescript/native" must be "npm:typescript@^7.x"; it provides the `tsc` that `npm run typecheck` runs',
    ).toMatch(/^npm:typescript@\^?7\./);
    expect(installedVersion("@typescript/native")).toMatch(/^7\./);
  });

  it("links node_modules/.bin/tsc to the TypeScript 7 compiler", () => {
    // Both compatibility packages declare a `tsc` bin, and npm can link `.bin/tsc` to the TypeScript 6 one even
    // when the 7 compiler is installed (npm/cli#9868). `npm run typecheck` runs `.bin/tsc`, so check the link itself.
    const link = new URL("../node_modules/.bin/tsc", import.meta.url);
    const target = realpathSync(link);
    // On Windows the entry is a shim script that names its target instead of a symlink.
    const names = target.includes("@typescript") ? target : readFileSync(target, "utf8");
    expect(
      names,
      "node_modules/.bin/tsc must come from @typescript/native; run `npm ci` again or call the native compiler by its package path in the typecheck script",
    ).toContain("@typescript/native");
  });

  it("lets typescript-eslint load against the installed compiler API", () => {
    // eslint-config-next bundles its own typescript-eslint; load it the way eslint does. It throws on import when
    // the `typescript` package is a version it does not support.
    const fromEslintConfigNext = createRequire(
      new URL("../node_modules/eslint-config-next/package.json", import.meta.url),
    );
    expect(() => fromEslintConfigNext("typescript-eslint")).not.toThrow();
  });

  it("knows the checker that decides when the TypeScript 6 package can go", () => {
    expect(rangeReaches(">=4.8.4 <6.1.0", [7, 1, 0])).toBe(false);
    expect(rangeReaches(">=4.8.4 <7.0.0", [7, 1, 0])).toBe(false);
    expect(rangeReaches(">=4.8.4 <=7.1.0", [7, 1, 0])).toBe(true);
    expect(rangeReaches(">=4.8.4 <7.2.0", [7, 1, 0])).toBe(true);
    expect(rangeReaches(">=4.8.4", [7, 1, 0])).toBe(true);
  });

  it("is still needed: typescript-eslint has not admitted a TypeScript 7.1 peer yet", () => {
    const fromEslintConfigNext = createRequire(
      new URL("../node_modules/eslint-config-next/package.json", import.meta.url),
    );
    const manifest = fromEslintConfigNext("typescript-eslint/package.json") as {
      version: string;
      peerDependencies: { typescript: string };
    };
    const range = manifest.peerDependencies.typescript;
    expect(
      rangeReaches(range, [7, 1, 0]),
      `typescript-eslint ${manifest.version} now accepts TypeScript 7.1 (peer range "${range}"), so the TypeScript 6 compatibility package is no longer needed. Finish TODO.md T-731: set "typescript" to the same 7.x as "@typescript/native", remove "@typescript/native", drop this file and the guard paragraph in CLAUDE.md, then run lint, typecheck, test and build.`,
    ).toBe(false);
  });
});
