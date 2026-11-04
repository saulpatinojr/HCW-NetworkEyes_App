import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// npm refuses to install (EOVERRIDE) when an override for a package this app also depends on directly names a
// different range than the dependency. Dependabot raises the direct range first, so an override written as a literal
// range breaks its whole npm job the moment a newer version is published (postcss ^8.5.23 -> ^8.5.31). Writing the
// override as "$name" makes it follow the direct dependency. See "Overrides" in the npm package.json documentation.

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const direct = new Set<string>([...Object.keys(pkg.dependencies ?? {}), ...Object.keys(pkg.devDependencies ?? {})]);

type Overrides = { [name: string]: string | Overrides };

function conflicting(overrides: Overrides, path: string[] = [], owner?: string): string[] {
  return Object.entries(overrides).flatMap(([key, value]) => {
    // Keys may carry a range ("brace-expansion@^1.1.7"); the package name is what npm compares. In object form,
    // "." overrides the enclosing package itself.
    const name = key === "." && owner ? owner : key.replace(/(?<=.)@.*$/, "");
    if (typeof value === "object") return conflicting(value, [...path, key], name);
    return direct.has(name) && value !== `$${name}` ? [`${[...path, key].join(" > ")}: ${value}`] : [];
  });
}

describe("postcss-selector-parser", () => {
  // @tailwindcss/typography 0.5.20 pins postcss-selector-parser to exactly 6.0.10, which has a quadratic-time flaw in
  // flat selector parsing (CVE-2026-104844, Dependabot alert 46, fixed in 7.1.6). The override in package.json lifts it;
  // this fails if the lockfile ever resolves an older one again (for example when the override is dropped by mistake).
  it("resolves to 7.1.6 or later", () => {
    const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
    const versions = Object.entries<{ version: string }>(lock.packages)
      .filter(([path]) => path.endsWith("node_modules/postcss-selector-parser"))
      .map(([, entry]) => entry.version);
    expect(versions.length).toBeGreaterThan(0);
    for (const version of versions) {
      const [major, minor, patch] = version.split(".").map(Number);
      const ok = major > 7 || (major === 7 && (minor > 1 || (minor === 1 && patch >= 6)));
      expect(ok, `postcss-selector-parser ${version} is below 7.1.6`).toBe(true);
    }
  });
});

describe("minimatch", () => {
  // minimatch below 11.0.1 can spend excessive CPU on a crafted glob pattern (GHSA-g3hv-75wg-m249, moderate). Dependabot
  // could not update it (its only path downgraded eslint 10 to 4), so the "minimatch@^10" override lifts the copy that
  // eslint, @eslint/config-array and @typescript-eslint/typescript-estree share to 11.x, which they call the same way.
  // The 3.x copy under eslint-config-next stays: eslint-plugin-import, -jsx-a11y and -react call minimatch 3's default
  // export, which 11 no longer has. It is lint-time only (not in any image), and its patterns come from this repository's
  // own lint configuration. This fails if anything other than that one 3.x copy resolves below 11.0.1.
  it("resolves to 11.0.1 or later outside eslint-config-next's own 3.x copy", () => {
    const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
    const entries = Object.entries<{ version: string }>(lock.packages).filter(([path]) =>
      path.endsWith("node_modules/minimatch"),
    );
    expect(entries.length).toBeGreaterThan(0);
    for (const [path, { version }] of entries) {
      if (path === "node_modules/eslint-config-next/node_modules/minimatch") continue;
      const [major, minor, patch] = version.split(".").map(Number);
      const ok = major > 11 || (major === 11 && (minor > 0 || patch >= 1));
      expect(ok, `${path} is minimatch ${version}, below 11.0.1`).toBe(true);
    }
  });
});

describe("package.json overrides", () => {
  it("finds a literal range in the object form too", () => {
    // The checker itself: "." under a directly used package overrides that package, nested keys override its dependencies.
    const name = [...direct][0];
    expect(conflicting({ [name]: { ".": "^1.0.0" } })).toEqual([`${name} > .: ^1.0.0`]);
    expect(conflicting({ [name]: { ".": `$${name}` } })).toEqual([]);
    expect(conflicting({ [name]: { "some-transitive-package": "^1.0.0" } })).toEqual([]);
  });


  it("follow the direct dependency with $name instead of repeating its range", () => {
    expect(
      conflicting(pkg.overrides ?? {}),
      'write each of these as "$<package>"; a literal range makes `npm install` fail with EOVERRIDE when Dependabot bumps the direct dependency',
    ).toEqual([]);
  });
});
