import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// npm 11 (bundled with Node.js 26) runs a dependency's install scripts (preinstall, install, postinstall) only when the
// `allowScripts` field of package.json covers that package; anything not covered is reported after `npm ci` and, in
// the npm releases that block by default, skipped. The decision for each package, read from its published tarball
// (TODO.md T-743 item 5; https://docs.npmjs.com/cli/v11/commands/npm-install-scripts):
//
//   @prisma/engines  true   postinstall downloads the Prisma schema engine and query engine for this platform; the
//                            Dockerfile's deps stage checks the engine is there, and the migrator needs the schema engine.
//   @prisma/client   true   postinstall runs `prisma generate`; `npm run typecheck` and the tests in CI need the
//                            generated client (the 300 `web` job runs no `prisma generate` of its own).
//   prisma           false  preinstall only refuses Node.js older than 18.18; package.json `engines` already says more.
//   unrs-resolver    false  postinstall only fetches the native binding from the registry, outside the lockfile, when
//                            the platform package is missing; npm installs that package from the lockfile instead.
//
// Approvals are name-only (`npm install-scripts approve <pkg> --no-allow-scripts-pin`), so a Dependabot bump of Prisma
// keeps them; package-lock.json's integrity hashes are what pin the code that runs. Change an entry with
// `npm install-scripts approve <pkg> --no-allow-scripts-pin` or `npm install-scripts deny <pkg>`, never by hand.

const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));

type LockEntry = { hasInstallScript?: boolean; optional?: boolean; os?: string[] };

describe("install scripts (npm allowScripts)", () => {
  it("allows exactly the Prisma engine download and client generation, and denies the rest", () => {
    expect(pkg.allowScripts).toEqual({
      "@prisma/client": true,
      "@prisma/engines": true,
      prisma: false,
      "unrs-resolver": false,
    });
  });

  it("covers every locked package that has an install script", () => {
    const covered = new Set(Object.keys(pkg.allowScripts ?? {}));
    const uncovered = Object.entries(lock.packages as Record<string, LockEntry>)
      // A platform-only optional package (fsevents, macOS) is not installed on Linux, so npm never runs or reports it.
      .filter(([, entry]) => entry.hasInstallScript && !(entry.optional && entry.os))
      .map(([location]) => location.slice(location.lastIndexOf("node_modules/") + "node_modules/".length))
      .filter((name) => !covered.has(name));
    expect(
      uncovered,
      "read what each script does, then run `npm install-scripts approve <pkg> --no-allow-scripts-pin` or " +
        "`npm install-scripts deny <pkg>` and record the reason in this file",
    ).toEqual([]);
  });
});
