// ──────────────────────────────────────────────────────────────────────────────
// Stat Master record shape (Phase F frontend mirror of cna/core/stat_masters.py,
// Phase C). Flat fact records: 8 dimensions + 3 measures.
// ──────────────────────────────────────────────────────────────────────────────

export type TrafficDirection = "east_west" | "north_south" | "management" | "unclassified";

export interface StatMasterRecord {
  // Dimensions
  traffic_direction: TrafficDirection;
  severity: string;
  framework: string;
  region: string;
  subscription_id: string;
  resource_type: string;
  category: string;
  rule_id: string;
  // Measures
  finding_count: number;
  resource_count: number;
  est_monthly_cost_impact: number;
}

export const STAT_DIMENSIONS = [
  "traffic_direction",
  "severity",
  "framework",
  "region",
  "subscription_id",
  "resource_type",
  "category",
  "rule_id",
] as const;
export type StatDimension = (typeof STAT_DIMENSIONS)[number];

export const STAT_MEASURES = [
  "finding_count",
  "resource_count",
  "est_monthly_cost_impact",
] as const;
export type StatMeasure = (typeof STAT_MEASURES)[number];

export const DIMENSION_LABELS: Record<StatDimension, string> = {
  traffic_direction: "Traffic Direction",
  severity: "Severity",
  framework: "Framework",
  region: "Region",
  subscription_id: "Subscription",
  resource_type: "Resource Type",
  category: "Category",
  rule_id: "Rule ID",
};

export const MEASURE_LABELS: Record<StatMeasure, string> = {
  finding_count: "Findings",
  resource_count: "Resources",
  est_monthly_cost_impact: "Est. Monthly Cost ($)",
};
