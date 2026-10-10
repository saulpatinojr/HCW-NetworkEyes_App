#!/usr/bin/env node
// Build-time filter for shape-index.json. Reads the source index, drops any
// entry whose style prefix is not in the pinned ALLOWED_LIBS set, and writes
// the filtered file back. Run from the cna-web image build (Dockerfile).
//
// Usage:
//   node scripts/filter-shape-index.mjs lib/drawio-mcp/shape-index.json

import { promises as fs } from "node:fs";
import path from "node:path";
import process from "node:process";

// Keep in lockstep with lib/drawio-mcp/allow-list.ts and
// cna/diagram_engine/shape_catalog.py: Azure icons are SVG image paths
// (there is no mxgraph.azure2 stencil set — it renders as a blank blue box),
// AWS icons are aws4 stencils.
const ALLOWED_LIBS = ["azure2", "aws4"];
const STENCIL_RE = /shape=mxgraph\.([a-z0-9]+)\./i;
const IMAGE_RE = /image=img\/lib\/([a-z0-9]+)\//i;
const STENCIL_LIBS = ["aws4"];

function libOf(style) {
  const img = style.match(IMAGE_RE);
  if (img) return img[1].toLowerCase();
  const stencil = style.match(STENCIL_RE);
  if (stencil && STENCIL_LIBS.includes(stencil[1].toLowerCase())) {
    return stencil[1].toLowerCase();
  }
  return null;
}

async function main() {
  const target = process.argv[2] ?? "lib/drawio-mcp/shape-index.json";
  const abs = path.resolve(target);
  const raw = await fs.readFile(abs, "utf8");
  const entries = JSON.parse(raw);
  if (!Array.isArray(entries)) {
    throw new Error(`expected array in ${abs}`);
  }
  const before = entries.length;
  const kept = entries.filter((e) => {
    const lib = libOf(e.style ?? "");
    return lib !== null && ALLOWED_LIBS.includes(lib);
  });
  const dropped = before - kept.length;
  await fs.writeFile(abs, JSON.stringify(kept, null, 2) + "\n", "utf8");
  console.log(
    `filter-shape-index: kept ${kept.length}/${before} entries (dropped ${dropped}); libs=${ALLOWED_LIBS.join(",")}`,
  );
}

main().catch((err) => {
  console.error("filter-shape-index failed:", err);
  process.exit(1);
});
