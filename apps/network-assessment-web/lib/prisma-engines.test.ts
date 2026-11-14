import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// prisma-engines.sha256 records the fingerprints (sha256) of the Prisma engines the images keep, and the Dockerfile's
// deps, builder and migrator-deps stages fail the build when a downloaded engine differs (TODO.md T-744). A Prisma
// update changes the engines, so this test fails first, in the pull request, when the file still names another
// @prisma/engines version than package-lock.json: the fix is one command, not a failed image build.

const FIX =
  "run `node scripts/prisma-engine-hashes.mjs --write` in apps/network-assessment-web (bash or PowerShell) and commit " +
  "prisma-engines.sha256";

const fingerprints = readFileSync(new URL("../prisma-engines.sha256", import.meta.url), "utf8");
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
const packages = lock.packages as Record<string, { version: string; dependencies?: Record<string, string> }>;

const header = (key: string) => fingerprints.match(new RegExp(`^# ${key}: (\\S+)$`, "m"))?.[1];
const entries = fingerprints
  .split("\n")
  .filter((line) => line !== "" && !line.startsWith("#"));

describe("Prisma engine fingerprints (prisma-engines.sha256)", () => {
  it("name the @prisma/engines version package-lock.json installs", () => {
    expect(header("@prisma/engines"), FIX).toBe(packages["node_modules/@prisma/engines"].version);
  });

  it("name the engine commit that @prisma/engines downloads", () => {
    const enginesVersion = packages["node_modules/@prisma/engines-version"].version;
    expect(packages["node_modules/@prisma/engines"].dependencies?.["@prisma/engines-version"]).toBe(enginesVersion);
    expect(header("engines-commit"), FIX).toBe(enginesVersion.split(".").pop());
  });

  it("hold one sha256sum line for each engine of the images' platform", () => {
    const target = header("binary-target");
    expect(target).toBe("debian-openssl-3.0.x");
    expect(entries.map((line) => line.replace(/^[0-9a-f]{64} {2}/, "<sha256>  "))).toEqual([
      `<sha256>  libquery_engine-${target}.so.node`,
      `<sha256>  schema-engine-${target}`,
    ]);
  });
});
