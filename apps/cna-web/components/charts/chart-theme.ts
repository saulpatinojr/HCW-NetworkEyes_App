// ──────────────────────────────────────────────────────────────────────────────
// CBTS chart palette constants (Phase F)
// Severity hexes mirror presentation/_lib/metrics.ts SEV_COLORS.
// ──────────────────────────────────────────────────────────────────────────────

export const CBTS_NAVY = "#012638";
export const CBTS_DARK_TEAL = "#004e3d";
export const CBTS_BRIGHT_TEAL = "#00e9bb";
export const CBTS_ORANGE = "#ffac00";
export const CBTS_WARM_GRAY = "#f2f1ed";

/** Grid / axis line color used by the existing SVG charts (dark glass panels). */
export const CHART_GRID = "#1e2d3d";
/** Muted label text color used by the existing SVG charts. */
export const CHART_TEXT = "#94a3b8";
export const CHART_TEXT_DIM = "#64748b";

/** Matches SEV_COLORS[*].hex in presentation/_lib/metrics.ts */
export const SEVERITY_HEX: Record<string, string> = {
  CRITICAL: "#ef4444",
  HIGH: "#f97316",
  MEDIUM: "#f59e0b",
  LOW: "#60a5fa",
  INFORMATIONAL: "#64748b",
};

export const SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"] as const;

/** Rotating palette for categorical series (categories, regions, …). */
export const CATEGORY_PALETTE = [
  CBTS_BRIGHT_TEAL,
  CBTS_ORANGE,
  "#60a5fa",
  "#a78bfa",
  "#f97316",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  CBTS_DARK_TEAL,
  "#64748b",
];

export const TRAFFIC_DIRECTION_HEX: Record<string, string> = {
  east_west: CBTS_BRIGHT_TEAL,
  north_south: CBTS_ORANGE,
  management: "#60a5fa",
  unclassified: "#64748b",
};

export const TRAFFIC_DIRECTION_LABELS: Record<string, string> = {
  east_west: "East-West",
  north_south: "North-South",
  management: "Management",
  unclassified: "Unclassified",
};
