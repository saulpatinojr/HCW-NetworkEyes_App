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
// fail first, with the fix written in the message. Remove them when typescript-eslint supports the TypeScript 7.1 API.

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const devDependencies: Record<string, string> = pkg.devDependencies;

function installedVersion(name: string): string {
  const file = new URL(`../node_modules/${name}/package.json`, import.meta.url);
  return JSON.parse(readFileSync(file, "utf8")).version;
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
});
