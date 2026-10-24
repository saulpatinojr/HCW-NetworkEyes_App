import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// npm refuses to install (EOVERRIDE) when an override for a package this app also depends on directly names a
// different range than the dependency. Dependabot raises the direct range first, so an override written as a literal
// range breaks its whole npm job the moment a newer version is published (postcss ^8.5.23 -> ^8.5.31). Writing the
// override as "$name" makes it follow the direct dependency. See "Overrides" in the npm package.json documentation.

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const direct = new Set<string>([...Object.keys(pkg.dependencies ?? {}), ...Object.keys(pkg.devDependencies ?? {})]);

type Overrides = { [name: string]: string | Overrides };

function conflicting(overrides: Overrides, path: string[] = []): string[] {
  return Object.entries(overrides).flatMap(([key, value]) => {
    // Keys may carry a range ("brace-expansion@^1.1.7"); the package name is what npm compares.
    const name = key.replace(/(?<=.)@.*$/, "");
    if (typeof value === "object") return conflicting(value, [...path, key]);
    return direct.has(name) && value !== `$${name}` ? [`${[...path, key].join(" > ")}: ${value}`] : [];
  });
}

describe("package.json overrides", () => {
  it("follow the direct dependency with $name instead of repeating its range", () => {
    expect(
      conflicting(pkg.overrides ?? {}),
      'write each of these as "$<package>"; a literal range makes `npm install` fail with EOVERRIDE when Dependabot bumps the direct dependency',
    ).toEqual([]);
  });
});
