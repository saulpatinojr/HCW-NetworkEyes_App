import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// npm runs a dependency's install scripts (preinstall, install, postinstall) according to the `allowScripts` field of
// package.json. npm 12 blocks a script that field does not cover; npm 11.20 and 11.21 (bundled with Node.js 26) still
// run it and only warn. `strict-allow-scripts=true` in this folder's .npmrc makes an uncovered script fail `npm ci`
// here now, before any script runs (error ESTRICTALLOWSCRIPTS). The decision for each package, read from its published
// tarball (TODO.md T-743 item 5; https://docs.npmjs.com/cli/v11/commands/npm-install-scripts):
//
//   @prisma/engines  true   postinstall downloads the Prisma schema engine and query engine for this platform; the
//                            Dockerfile's deps stage checks the engine is there, and the migrator needs the schema engine.
//   @prisma/client   true   postinstall runs `prisma generate`; `npm run typecheck` and the tests in CI need the
//                            generated client (the 300 `web` job runs no `prisma generate` of its own).
//   prisma           false  preinstall only refuses Node.js older than 18.18; package.json `engines` already says more.
//   unrs-resolver    false  postinstall only fetches the native binding from the registry, outside the lockfile, when
//                            the platform package is missing; npm installs that package from the lockfile instead.
//
// Approvals are name-only (`npm install-scripts approve <pkg> --no-allow-scripts-pin`), on purpose. With strict mode on,
// a version-pinned approval that no longer matches fails `npm ci`, so every Prisma bump from Dependabot would go red until
// someone re-approved on the bot's branch. The pin would add little: package-lock.json's integrity hashes already pin
// the exact code that runs, a bump arrives as a reviewed pull request, strict mode blocks the script of any package not
// named here, and a pin would not cover the engine binary @prisma/engines downloads anyway. Change an entry with
// `npm install-scripts approve <pkg> --no-allow-scripts-pin` or `npm install-scripts deny <pkg>`, never by hand.

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));

type LockEntry = {
  name?: string;
  hasInstallScript?: boolean;
  optional?: boolean;
  os?: string[];
  cpu?: string[];
  libc?: string[];
};

// The CI runner and the images are linux / x64 / glibc. A list like ["darwin"] or ["!linux"] excludes a value.
const excludes = (list: string[] | undefined, value: string) =>
  list !== undefined &&
  (list.includes(`!${value}`) || (list.some((v) => !v.startsWith("!")) && !list.includes(value)));

// An optional package that cannot install on linux / x64 / glibc never has its script run or checked there.
const installsHere = (entry: LockEntry) =>
  !(
    entry.optional &&
    (excludes(entry.os, "linux") || excludes(entry.cpu, "x64") || excludes(entry.libc, "glibc"))
  );

describe("install scripts (npm allowScripts)", () => {
  it("allows exactly the Prisma engine download and client generation, and denies the rest", () => {
    expect(pkg.allowScripts).toEqual({
      "@prisma/client": true,
      "@prisma/engines": true,
      prisma: false,
      "unrs-resolver": false,
    });
  });

  it("treats only packages that cannot install on linux / x64 / glibc as not installed", () => {
    expect(installsHere({ optional: true, os: ["darwin"] })).toBe(false);
    expect(installsHere({ optional: true, os: ["!linux"] })).toBe(false);
    expect(installsHere({ optional: true, cpu: ["arm64"] })).toBe(false);
    expect(installsHere({ optional: true, os: ["linux"], libc: ["musl"] })).toBe(false);
    expect(installsHere({ optional: true, os: ["linux", "darwin"], cpu: ["x64"], libc: ["glibc"] })).toBe(true);
    expect(installsHere({ optional: true, os: ["!win32"] })).toBe(true);
    expect(installsHere({ os: ["darwin"] })).toBe(true);
  });

  it("covers every locked package that has an install script", () => {
    const covered = new Set(Object.keys(pkg.allowScripts ?? {}));
    const uncovered = Object.entries(lock.packages as Record<string, LockEntry>)
      // fsevents (optional, os ["darwin"]) is left out by this rule: it never installs on Linux.
      .filter(([, entry]) => entry.hasInstallScript && installsHere(entry))
      // An npm: alias is installed under its alias path; the lockfile's `name` is the real package.
      .map(([location, entry]) => entry.name ?? location.slice(location.lastIndexOf("node_modules/") + "node_modules/".length))
      .filter((name) => !covered.has(name));
    expect(
      uncovered,
      "read what each script does, then run `npm install-scripts approve <pkg> --no-allow-scripts-pin` or " +
        "`npm install-scripts deny <pkg>` and record the reason in this file",
    ).toEqual([]);
  });
});
