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
  // minimatch 7.0.0 to 11.0.0 can spend excessive CPU on a crafted glob pattern (GHSA-g3hv-75wg-m249, moderate). Dependabot
  // could not update it (its only path downgraded eslint 10 to 4), so the "minimatch@^10" override lifts the copy that
  // eslint, @eslint/config-array and @typescript-eslint/typescript-estree share to 11.x, which they call the same way.
  // The 3.x copy under eslint-config-next stays: eslint-plugin-import 2.32.0, -jsx-a11y 6.10.2 and -react 7.37.5 (the
  // newest of each on 2026-11-04) require minimatch ^3.1.2 and call it as a function (its default export) and through
  // `makeRe`; minimatch 11's CommonJS export is an object with neither, so an override would break those rules. Since
  // 2026-11-04 GitHub and the npm registry both list that advisory as ">= 7.0.0, < 11.0.1", so 3.x is outside it and
  // `npm audit` is clean. The 3.x advisories that do exist (GHSA-3ppc-4f35-3m26 and GHSA-7r86-cg39-jmmj below 3.1.3,
  // GHSA-23c5-xmqv-rm74 below 3.1.4) are what the second check guards. It is lint-time only (not in any image), and its
  // patterns come from this repository's own lint configuration.
  const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
  const entries = Object.entries<{ version: string }>(lock.packages).filter(([path]) =>
    path.endsWith("node_modules/minimatch"),
  );
  const pluginCopy = "node_modules/eslint-config-next/node_modules/minimatch";

  it("resolves to 11.0.1 or later outside eslint-config-next's own 3.x copy", () => {
    expect(entries.length).toBeGreaterThan(0);
    for (const [path, { version }] of entries) {
      if (path === pluginCopy) continue;
      const [major, minor, patch] = version.split(".").map(Number);
      const ok = major > 11 || (major === 11 && (minor > 0 || patch >= 1));
      expect(ok, `${path} is minimatch ${version}, below 11.0.1`).toBe(true);
    }
  });

  it("keeps eslint-config-next's 3.x copy, while it exists, at 3.1.4 or later", () => {
    // No entry is fine too: that is the plugins having moved off minimatch 3, which ends this exception for good.
    const entry = entries.find(([path]) => path === pluginCopy);
    if (!entry) return;
    const [major, minor, patch] = entry[1].version.split(".").map(Number);
    const ok = major > 3 || (major === 3 && (minor > 1 || (minor === 1 && patch >= 4)));
    expect(ok, `${pluginCopy} is minimatch ${entry[1].version}, below 3.1.4`).toBe(true);
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
