import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

// NetworkEyes stands alone: it builds and publishes its own images and the web tier knows nothing about any other
// repository's workflows, labels or deployment code. The Updates page only compares the running build with the
// registry the image came from; how a newer image is deployed is up to whoever deploys it.
//
// This guard fails if a file under apps/network-assessment-web names another repository, one of its workflows or its issue label,
// or the settings that used to link to them. This file is the one place allowed to spell those strings out.

const APP_ROOT = fileURLToPath(new URL("..", import.meta.url));
const THIS_FILE = path.resolve(fileURLToPath(import.meta.url));
const SKIPPED_DIRECTORIES = new Set(["node_modules", ".next", ".git", "coverage", "dist"]);
const MAX_FILE_BYTES = 2_000_000;

type Forbidden = { name: string; pattern: RegExp };

const FORBIDDEN: readonly Forbidden[] = [
  { name: "Work-Cloud_", pattern: /Work-Cloud_/ },
  { name: "saulpatino-cbts", pattern: /saulpatino-cbts/ },
  { name: "230-image-update", pattern: /230-image-update/ },
  { name: "210-deploy", pattern: /210-deploy/ },
  // The quoted token "update-available" is the web tier's own verdict value (UpdateVerdict) and stays. What must not
  // come back is the label of another repository's update-request issues, which is never written inside quotes.
  { name: "update-available (issue label)", pattern: /(?<!["'])update-available/ },
  { name: "NETWORK_ASSESSMENT_APPLIANCE_REPO", pattern: /NETWORK_ASSESSMENT_APPLIANCE_REPO/ },
  { name: "NETWORK_ASSESSMENT_GITHUB_SERVER_URL", pattern: /NETWORK_ASSESSMENT_GITHUB_SERVER_URL/ },
  { name: "applianceLinks", pattern: /applianceLinks/ },
];

function violationsIn(text: string): string[] {
  return FORBIDDEN.filter(({ pattern }) => pattern.test(text)).map(({ name }) => name);
}

function* walk(directory: string): Generator<string> {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!SKIPPED_DIRECTORIES.has(entry.name)) yield* walk(path.join(directory, entry.name));
    } else if (entry.isFile()) {
      yield path.join(directory, entry.name);
    }
  }
}

function readText(file: string): string | null {
  if (statSync(file).size > MAX_FILE_BYTES) return null;
  const bytes = readFileSync(file);
  return bytes.includes(0) ? null : bytes.toString("utf8");
}

describe("the web tier does not depend on another repository", () => {
  it("matches every forbidden name and lets the verdict value through", () => {
    expect(violationsIn("saulpatino-cbts/Work-Cloud_Network_Azure_Appliance")).toEqual([
      "Work-Cloud_",
      "saulpatino-cbts",
    ]);
    expect(violationsIn("actions/workflows/230-image-update.yml")).toEqual(["230-image-update"]);
    expect(violationsIn("actions/workflows/210-deploy.yml")).toEqual(["210-deploy"]);
    expect(violationsIn("process.env.NETWORK_ASSESSMENT_APPLIANCE_REPO")).toEqual(["NETWORK_ASSESSMENT_APPLIANCE_REPO"]);
    expect(violationsIn("process.env.NETWORK_ASSESSMENT_GITHUB_SERVER_URL")).toEqual(["NETWORK_ASSESSMENT_GITHUB_SERVER_URL"]);
    expect(violationsIn("applianceLinks(repo, url)")).toEqual(["applianceLinks"]);
    for (const labelUse of [
      "label:update-available",
      "label%3Aupdate-available",
      "an `update-available` issue",
      '<span className="font-mono">update-available</span>',
    ]) {
      expect(violationsIn(labelUse), labelUse).toEqual(["update-available (issue label)"]);
    }
    for (const verdictUse of ['"update-available"', "'update-available'", 'verdict === "update-available"']) {
      expect(violationsIn(verdictUse), verdictUse).toEqual([]);
    }
  });

  it("finds no such reference in any file under apps/network-assessment-web", () => {
    const offenders: string[] = [];
    let scanned = 0;
    for (const file of walk(APP_ROOT)) {
      if (path.resolve(file) === THIS_FILE) continue;
      const text = readText(file);
      if (text === null) continue;
      scanned += 1;
      const found = violationsIn(text);
      if (found.length > 0) offenders.push(`${path.relative(APP_ROOT, file)}: ${found.join(", ")}`);
    }
    expect(scanned).toBeGreaterThan(100);
    expect(offenders).toEqual([]);
  });

  it("keeps the update check on the registry API of the configured image", () => {
    for (const name of ["image-update.ts", "image-update-rules.ts"]) {
      const text = readFileSync(path.join(APP_ROOT, "lib", name), "utf8");
      expect(text, name).not.toMatch(/github/i);
      expect(text, name).not.toMatch(/process\.env\.NETWORK_ASSESSMENT_(?!BUILD_SHA|WEB_IMAGE|IMAGE_REGISTRY_(?:USERNAME|TOKEN)|IMAGE_UPDATE_CHECK_INTERVAL_MINUTES)/);
    }
  });
});
