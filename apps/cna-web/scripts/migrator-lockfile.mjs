#!/usr/bin/env node
// Build-time helper for the Dockerfile "migrator-deps" stage (TODO.md T-737).
//
// The migrator image runs `prisma migrate deploy` and prisma/seed-local-admin.js and nothing else, so its
// node_modules must hold the Prisma CLI, @prisma/client and what they depend on, and none of the web app's
// build tooling or runtime. This script cuts that closure out of the web app's package-lock.json:
//
//   node scripts/migrator-lockfile.mjs <source-dir> <output-dir>
//
// It reads <source-dir>/package.json and <source-dir>/package-lock.json and writes a package.json and a
// package-lock.json to <output-dir>. Every kept entry is copied from the web lockfile as it is (version,
// resolved URL, integrity hash, nesting), so `npm ci` in <output-dir> installs exactly the versions the web app
// is audited and tested with. `npm ci` also refuses a lockfile that does not match its package.json, so a
// package this script missed fails the image build instead of being fetched unpinned.
//
// The closure follows `dependencies`, `optionalDependencies` and the non-optional `peerDependencies`, the same
// edges npm installs. A package the web app reaches only through an optional peer (typescript, through
// @prisma/client) is therefore not part of it.

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

// The packages migrate.sh and seed-local-admin.js load; their version ranges come from package.json.
export const MIGRATOR_ROOTS = ["prisma", "@prisma/client"];

// Where npm would find `name` for the package at `from` ("" is the root): its own node_modules, then each
// enclosing one, up to the top level.
function locate(packages, from, name) {
  let base = from;
  for (;;) {
    const candidate = `${base ? `${base}/` : ""}node_modules/${name}`;
    if (packages[candidate]) return candidate;
    if (base === "") return null;
    const cut = base.lastIndexOf("/node_modules/");
    base = cut === -1 ? "" : base.slice(0, cut);
  }
}

export function buildMigratorManifest(pkg, lock, roots = MIGRATOR_ROOTS) {
  const packages = lock.packages ?? {};
  const dependencies = {};
  for (const name of roots) {
    const range = pkg.dependencies?.[name];
    if (!range) {
      throw new Error(`${name} must be a production dependency in package.json (the migrator runs it)`);
    }
    dependencies[name] = range;
  }

  const manifestExtras = {};
  const kept = new Set();
  const queue = [];
  const enqueue = (from, name, required) => {
    const location = locate(packages, from, name);
    if (location === null) {
      if (required) throw new Error(`${name} (needed by "${from || "the root"}") is not in package-lock.json`);
      return;
    }
    if (!kept.has(location)) {
      kept.add(location);
      queue.push(location);
    }
  };

  for (const name of roots) enqueue("", name, true);
  while (queue.length > 0) {
    const location = queue.shift();
    const entry = packages[location];
    for (const name of Object.keys(entry.dependencies ?? {})) enqueue(location, name, true);
    for (const name of Object.keys(entry.optionalDependencies ?? {})) enqueue(location, name, false);
    for (const name of Object.keys(entry.peerDependencies ?? {})) {
      const optional = entry.peerDependenciesMeta?.[name]?.optional === true;
      if (!optional) enqueue(location, name, true);
    }
  }

  // `npm ci` checks the lockfile against the edges of the manifest it sits next to. The web app's overrides pin some
  // of these packages to versions their parents do not ask for (deepmerge-ts), so the ones that touch this tree move
  // with it. Anything this script cannot copy verbatim is an error, not something to leave out.
  const keptNames = new Set([...kept].map((location) => location.slice(location.lastIndexOf("node_modules/") + 13)));
  const overrides = {};
  for (const [key, value] of Object.entries(pkg.overrides ?? {})) {
    const name = key.startsWith("@") ? `@${key.slice(1).split("@")[0]}` : key.split("@")[0];
    if (!keptNames.has(name)) continue;
    if (typeof value !== "string" || value.startsWith("$")) {
      throw new Error(`override "${key}" affects the migrator tree but is not a plain version range`);
    }
    overrides[key] = value;
  }
  if (Object.keys(overrides).length > 0) manifestExtras.overrides = overrides;

  const lockPackages = { "": { name: "cna-migrator", dependencies } };
  for (const location of [...kept].sort()) {
    // `dev` and `devOptional` describe the web app's tree, where these packages are reachable from devDependencies
    // as well; in this tree every one of them is a production dependency.
    const entry = { ...packages[location] };
    delete entry.dev;
    delete entry.devOptional;
    lockPackages[location] = entry;
  }

  return {
    manifest: { name: "cna-migrator", private: true, dependencies, ...manifestExtras },
    lockfile: { name: "cna-migrator", lockfileVersion: lock.lockfileVersion, requires: true, packages: lockPackages },
  };
}

function main(argv) {
  const [sourceDir, outputDir] = argv;
  if (!sourceDir || !outputDir) {
    console.error("usage: node scripts/migrator-lockfile.mjs <source-dir> <output-dir>");
    return 2;
  }
  const pkg = JSON.parse(readFileSync(path.join(sourceDir, "package.json"), "utf8"));
  const lock = JSON.parse(readFileSync(path.join(sourceDir, "package-lock.json"), "utf8"));
  const { manifest, lockfile } = buildMigratorManifest(pkg, lock);
  mkdirSync(outputDir, { recursive: true });
  writeFileSync(path.join(outputDir, "package.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  writeFileSync(path.join(outputDir, "package-lock.json"), `${JSON.stringify(lockfile, null, 2)}\n`);
  console.log(`migrator tree: ${Object.keys(lockfile.packages).length - 1} packages from package-lock.json`);
  return 0;
}

// Run only when started from the command line, so a test can import buildMigratorManifest.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2));
}
