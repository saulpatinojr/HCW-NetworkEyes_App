// ──────────────────────────────────────────────────────────────────────────────
// Chart palette constants (Phase F)
// Severity hexes mirror presentation/_lib/metrics.ts SEV_COLORS.
// ──────────────────────────────────────────────────────────────────────────────

export const PALETTE_NAVY = "#012638";
export const PALETTE_DARK_TEAL = "#004e3d";
export const PALETTE_BRIGHT_TEAL = "#00e9bb";
export const PALETTE_ORANGE = "#ffac00";
export const PALETTE_WARM_GRAY = "#f2f1ed";

/** Grid / axis line color — theme-aware CSS variable defined in globals.css. */
export const CHART_GRID = "var(--chart-grid)";
/** Muted label text color — theme-aware CSS variable defined in globals.css. */
export const CHART_TEXT = "var(--chart-text)";
export const CHART_TEXT_DIM = "var(--chart-text-dim)";

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
  PALETTE_BRIGHT_TEAL,
  PALETTE_ORANGE,
  "#60a5fa",
  "#a78bfa",
  "#f97316",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  PALETTE_DARK_TEAL,
  "#64748b",
];

export const TRAFFIC_DIRECTION_HEX: Record<string, string> = {
  east_west: PALETTE_BRIGHT_TEAL,
  north_south: PALETTE_ORANGE,
  management: "#60a5fa",
  unclassified: "#64748b",
};

export const TRAFFIC_DIRECTION_LABELS: Record<string, string> = {
  east_west: "East-West",
  north_south: "North-South",
  management: "Management",
  unclassified: "Unclassified",
};
