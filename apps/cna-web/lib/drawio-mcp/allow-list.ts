// Icon library allow-list. Pinned per the Draw.io integration plan.
// To change sets, update here AND the Python client AND the build-time filter
// in scripts/filter-shape-index.mjs.
//
// Two icon mechanisms, one per cloud — mirrors cna/diagram_engine/shape_catalog.py,
// and reflects what draw.io actually renders (verified 2026-08-28 by exporting
// every catalogued style with the headless draw.io CLI):
//
//   AWS   shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<name>
//         The aws4 stencil set is real; an unknown <name> draws a blank square.
//   Azure image=img/lib/azure2/<category>/<File_Name>.svg
//         There is NO mxgraph.azure2 stencil namespace. `shape=mxgraph.azure2.*`
//         silently degrades to a plain blue rectangle, which is what this app
//         shipped until 2026-08-28 — so it is rejected here on purpose.

export const ALLOWED_LIBS = ["azure2", "aws4"] as const;

export type AllowedLib = (typeof ALLOWED_LIBS)[number];

const STENCIL_RE = /shape=mxgraph\.([a-z0-9]+)\./i;
const IMAGE_RE = /image=img\/lib\/([a-z0-9]+)\//i;

/** Stencil namespaces draw.io actually ships (azure2 is not one — see above). */
const STENCIL_LIBS: readonly string[] = ["aws4"];

/** Return the icon library a style draws from, or null if it draws from none. */
export function libOf(style: string): string | null {
  const img = style.match(IMAGE_RE);
  if (img) return img[1].toLowerCase();
  const stencil = style.match(STENCIL_RE);
  if (stencil && STENCIL_LIBS.includes(stencil[1].toLowerCase())) {
    return stencil[1].toLowerCase();
  }
  return null;
}

/** True iff a style string belongs to an allow-listed library. */
export function isAllowedStyle(style: string): boolean {
  const lib = libOf(style);
  return lib !== null && (ALLOWED_LIBS as readonly string[]).includes(lib);
}
