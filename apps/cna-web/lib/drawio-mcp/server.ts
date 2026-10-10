import { ALLOWED_LIBS, isAllowedStyle, type AllowedLib } from "./allow-list";
import rawIndex from "./shape-index.json";

export interface ShapeEntry {
  name: string;
  library: string;
  tags: string[];
  style: string;
}

export interface ShapeSearchHit extends ShapeEntry {
  score: number;
}

// Filter at module-load time. Layer #2 of triple-enforced library pinning
// (Dockerfile is #1, route handler is #3).
const INDEX: ShapeEntry[] = (rawIndex as ShapeEntry[]).filter((e) =>
  isAllowedStyle(e.style),
);

/** Test-only hook. The in-memory index is immutable in production. */
export function _getIndexForTest(): ShapeEntry[] {
  return INDEX;
}

function scoreEntry(entry: ShapeEntry, terms: string[]): number {
  const hay = [entry.name, entry.library, ...entry.tags].join(" ").toLowerCase();
  let score = 0;
  for (const t of terms) {
    if (!t) continue;
    if (entry.name.toLowerCase() === t) score += 100;
    if (entry.name.toLowerCase().includes(t)) score += 30;
    if (entry.tags.some((tag) => tag.toLowerCase() === t)) score += 20;
    if (hay.includes(t)) score += 5;
  }
  return score;
}

export async function searchShapes(
  query: string,
  limit = 20,
): Promise<ShapeSearchHit[]> {
  const terms = query
    .toLowerCase()
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
  if (terms.length === 0) return [];
  const scored: ShapeSearchHit[] = [];
  for (const entry of INDEX) {
    const score = scoreEntry(entry, terms);
    if (score > 0) scored.push({ ...entry, score });
  }
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, Math.max(1, Math.min(limit, 100)));
}

export interface CreateDiagramResult {
  /** XML bytes echoed back (caller persists / renders). */
  xml: string;
  /** Suggested filename stem (no extension). */
  name: string;
  /** Embed URL that loads the XML into the public viewer.diagrams.net iframe. */
  embedUrl: string;
}

/**
 * "Create" a diagram. We do not run a draw.io editor server here — we accept
 * XML, validate it, and return an embed URL that the in-portal viewer uses.
 * The Python pipeline still owns rendering to SVG/PNG/PDF.
 */
export function createDiagram(xml: string, name = "diagram"): CreateDiagramResult {
  if (!xml || !xml.includes("<mxfile") || !xml.includes("</mxfile>")) {
    throw new Error("create_diagram: payload does not look like draw.io XML");
  }
  const safeName = name.replace(/[^a-zA-Z0-9._-]/g, "-").slice(0, 80) || "diagram";
  // viewer.diagrams.net accepts XML via the URL fragment for short payloads,
  // but for large topologies we rely on the iframe postMessage protocol —
  // the URL below opens an empty viewer that the React component then feeds.
  const embedUrl =
    "https://viewer.diagrams.net/?embed=1&proto=json&spin=1&libraries=1";
  return { xml, name: safeName, embedUrl };
}

export function listIconLibs(): readonly AllowedLib[] {
  return ALLOWED_LIBS;
}
