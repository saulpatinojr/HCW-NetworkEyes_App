#!/usr/bin/env node
// Writes prisma-engines.sha256, the fingerprints (sha256) of the Prisma engines the web and migrator images keep
// (TODO.md T-744). Run it from apps/network-assessment-web after a Prisma update, in bash or PowerShell:
//
//   node scripts/prisma-engine-hashes.mjs --write     rewrite prisma-engines.sha256 for the locked Prisma version
//   node scripts/prisma-engine-hashes.mjs             print the file it would write, change nothing
//   node scripts/prisma-engine-hashes.mjs --check     exit 1 if prisma-engines.sha256 differs from what it would write
//
// What it does, for the @prisma/engines version and engine commit that package-lock.json names (no install needed):
//   1. downloads each engine for the images' platform from Prisma's own host, binaries.prisma.sh (never from
//      PRISMA_ENGINES_MIRROR, so a mirror cannot choose its own fingerprints), with the .sha256 files published beside it;
//   2. checks the compressed download against the published .gz.sha256, unpacks it, and checks the result against the
//      published .sha256;
//   3. where `npm ci` has installed that same engine in node_modules/@prisma/engines (Linux x64 with OpenSSL 3, as in
//      CI), checks the installed file has the same fingerprint too.
// Any disagreement stops it with an error and writes nothing. The fingerprints are then reviewed in the pull request;
// from then on, scripts/check-prisma-engines.sh fails any image build whose engines differ from them.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

const WEB_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUTPUT = path.join(WEB_DIR, "prisma-engines.sha256");

// Prisma's own download host. Deliberately not PRISMA_ENGINES_MIRROR (see the header).
const PRISMA_BINARIES_HOST = "https://binaries.prisma.sh";
// The platform of every image: 200-build-images.yml builds linux/amd64 only, on Debian 13 with OpenSSL 3.
// An arm64 image would need linux-arm64-openssl-3.0.x here and in the Dockerfile's comments.
export const BINARY_TARGET = "debian-openssl-3.0.x";

// The engines @prisma/engines' install script fetches (the query engine library and the schema engine): the name
// the file is installed under, and its name on the download host.
export const engineFiles = (target) => [
  { installed: `libquery_engine-${target}.so.node`, published: "libquery_engine.so.node" },
  { installed: `schema-engine-${target}`, published: "schema-engine" },
];

const HEADER = `# Fingerprints (sha256) of the Prisma engine files the web and migrator images keep (TODO.md T-744).
#
# @prisma/engines downloads these two programs while it installs, from binaries.prisma.sh (or PRISMA_ENGINES_MIRROR),
# and checks them only against .sha256 files served by the same host: that catches a broken download, not a
# substituted one. package-lock.json pins the npm packages but not these downloads. So the Dockerfile's deps, builder
# and migrator-deps stages run scripts/check-prisma-engines.sh, which checks every Prisma engine file in node_modules
# against the lines below (\`sha256sum -c\`) and fails the build on any difference.
#
# Written by scripts/prisma-engine-hashes.mjs; do not edit the lines by hand. After a Prisma update (Dependabot), from
# apps/network-assessment-web, in bash or PowerShell:
#   node scripts/prisma-engine-hashes.mjs --write
# lib/prisma-engines.test.ts fails until this file names the @prisma/engines version in package-lock.json.
#`;

const sha256 = (buffer) => createHash("sha256").update(buffer).digest("hex");

function fail(message) {
  console.error(`prisma-engine-hashes: ${message}`);
  process.exit(1);
}

// The @prisma/engines version and the engine commit it downloads, as package-lock.json pins them.
export function lockedEngines(lock) {
  const packages = lock.packages ?? {};
  const engines = packages["node_modules/@prisma/engines"];
  const enginesVersion = packages["node_modules/@prisma/engines-version"];
  if (!engines?.version || !enginesVersion?.version) {
    throw new Error("package-lock.json has no top-level @prisma/engines or @prisma/engines-version entry");
  }
  // @prisma/engines-version is published as <x.y.z>-<n>.<engine commit>.
  const commit = enginesVersion.version.split(".").pop();
  if (!/^[0-9a-f]{40}$/.test(commit)) {
    throw new Error(`cannot read the engine commit from @prisma/engines-version ${enginesVersion.version}`);
  }
  const wanted = engines.dependencies?.["@prisma/engines-version"];
  if (wanted && wanted !== enginesVersion.version) {
    throw new Error(`@prisma/engines ${engines.version} asks for @prisma/engines-version ${wanted}, the lock holds ${enginesVersion.version}`);
  }
  return { version: engines.version, commit };
}

export function renderFingerprints({ version, commit, target, hashes }) {
  const lines = engineFiles(target).map(({ installed }) => `${hashes[installed]}  ${installed}`);
  return `${HEADER}\n# @prisma/engines: ${version}\n# engines-commit: ${commit}\n# binary-target: ${target}\n${lines.join("\n")}\n`;
}

async function download(url) {
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok) fail(`${url} answered HTTP ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
}

async function publishedHash(url) {
  const text = (await download(url)).toString("utf8").trim();
  const hash = text.split(/\s+/)[0];
  if (!/^[0-9a-f]{64}$/.test(hash)) fail(`${url} does not hold a sha256 fingerprint`);
  return hash;
}

async function main(argv) {
  const mode = argv[0] ?? "--print";
  if (!["--print", "--write", "--check"].includes(mode) || argv.length > 1) {
    fail("usage: node scripts/prisma-engine-hashes.mjs [--write | --check]");
  }
  const lock = JSON.parse(readFileSync(path.join(WEB_DIR, "package-lock.json"), "utf8"));
  const { version, commit } = lockedEngines(lock);

  // If node_modules is installed, it must be the locked version, or its files say nothing about this one.
  const installedPackage = path.join(WEB_DIR, "node_modules", "@prisma", "engines", "package.json");
  const installedVersion = existsSync(installedPackage)
    ? JSON.parse(readFileSync(installedPackage, "utf8")).version
    : null;
  const compareInstalled = installedVersion === version;
  if (installedVersion && !compareInstalled) {
    console.error(`prisma-engine-hashes: node_modules holds @prisma/engines ${installedVersion}, the lock ${version}; run \`npm ci\` to compare with an install too.`);
  }

  const hashes = {};
  for (const { installed, published } of engineFiles(BINARY_TARGET)) {
    const base = `${PRISMA_BINARIES_HOST}/all_commits/${commit}/${BINARY_TARGET}/${published}`;
    const gz = await download(`${base}.gz`);
    const gzExpected = await publishedHash(`${base}.gz.sha256`);
    if (sha256(gz) !== gzExpected) fail(`${base}.gz does not match its published .gz.sha256`);
    const hash = sha256(gunzipSync(gz));
    const expected = await publishedHash(`${base}.sha256`);
    if (hash !== expected) fail(`${base}.gz unpacks to ${hash}, its published .sha256 says ${expected}`);
    const local = path.join(WEB_DIR, "node_modules", "@prisma", "engines", installed);
    if (compareInstalled && existsSync(local)) {
      const localHash = sha256(readFileSync(local));
      if (localHash !== hash) fail(`node_modules/@prisma/engines/${installed} is ${localHash}, the download ${hash}`);
      console.error(`prisma-engine-hashes: ${installed} matches the download, its published .sha256 and the local install`);
    } else {
      console.error(`prisma-engine-hashes: ${installed} matches the download and its published .sha256 (not installed here to compare)`);
    }
    hashes[installed] = hash;
  }

  const text = renderFingerprints({ version, commit, target: BINARY_TARGET, hashes });
  if (mode === "--write") {
    writeFileSync(OUTPUT, text);
    console.error(`prisma-engine-hashes: wrote prisma-engines.sha256 for @prisma/engines ${version}`);
  } else if (mode === "--check") {
    const current = existsSync(OUTPUT) ? readFileSync(OUTPUT, "utf8") : "";
    if (current !== text) fail("prisma-engines.sha256 is not what this script writes; run it with --write");
    console.error("prisma-engine-hashes: prisma-engines.sha256 is current");
  } else {
    process.stdout.write(text);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main(process.argv.slice(2));
}
