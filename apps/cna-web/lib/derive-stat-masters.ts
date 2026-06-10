// ──────────────────────────────────────────────────────────────────────────────
// Derive StatMasterRecords from Finding rows in TypeScript (Phase F interim).
// Once the Phase C metrics endpoint (`GET /metrics/{engagement}`) is live,
// pages should fetch pre-built records from the API instead and this module
// becomes a fallback. Fields added in Phase B (trafficDirection, framework,
// region, resourceType, estCostImpact) are read when present; older rows are
// classified heuristically and bucketed as "unclassified" when no signal.
// ──────────────────────────────────────────────────────────────────────────────

import type { StatMasterRecord, TrafficDirection } from "./types/stat-master";

/** Minimal Finding shape — superset-compatible with Prisma rows. */
export interface FindingLike {
  title: string;
  severity: string;
  category: string;
  description?: string | null;
  // Phase B optional enrichment fields (not yet in Prisma schema everywhere)
  trafficDirection?: string | null;
  framework?: string | null;
  region?: string | null;
  resourceType?: string | null;
  estCostImpact?: number | null;
  credentialId?: string | null;
}

const EAST_WEST_RE =
  /\b(nsg|network security group|peering|segmentation|subnet|spoke|route table|udr|user.defined route|east.west|lateral|vnet.to.vnet|hub.and.spoke)\b/i;
const NORTH_SOUTH_RE =
  /\b(public ip|internet|exposure|exposed|firewall|ddos|waf|application gateway|app gateway|vpn|expressroute|express route|nat gateway|perimeter|ingress|egress|north.south|inbound|outbound)\b/i;
const MANAGEMENT_RE =
  /\b(bastion|diagnostic|monitor|flow log|network watcher|log analytics|management|rbac|role.based|policy|governance)\b/i;

/** Deterministic heuristic mirror of cna/core/finding_taxonomy.py (Phase B). */
export function classifyTrafficDirection(f: FindingLike): TrafficDirection {
  const explicit = (f.trafficDirection ?? "").toLowerCase();
  if (explicit === "east_west" || explicit === "north_south" || explicit === "management") {
    return explicit;
  }
  const text = `${f.title} ${f.category} ${f.description ?? ""}`;
  if (NORTH_SOUTH_RE.test(text)) return "north_south";
  if (EAST_WEST_RE.test(text)) return "east_west";
  if (MANAGEMENT_RE.test(text)) return "management";
  return "unclassified";
}

const RULE_ID_RE = /\b([A-Z]{2,5}-[A-Z]{2,10}-\d{1,4})\b/;

export function extractRuleId(title: string): string {
  return RULE_ID_RE.exec(title)?.[1] ?? "—";
}

const RESOURCE_TYPE_PATTERNS: Array<[RegExp, string]> = [
  [/nsg|network security group/i, "NSG"],
  [/public ip/i, "Public IP"],
  [/firewall/i, "Firewall"],
  [/application gateway|app gateway|waf/i, "App Gateway"],
  [/load balancer/i, "Load Balancer"],
  [/vpn gateway/i, "VPN Gateway"],
  [/expressroute|express route/i, "ExpressRoute"],
  [/nat gateway/i, "NAT Gateway"],
  [/bastion/i, "Bastion"],
  [/private endpoint|private link/i, "Private Endpoint"],
  [/peering/i, "VNet Peering"],
  [/route table|udr/i, "Route Table"],
  [/subnet/i, "Subnet"],
  [/vnet|virtual network/i, "VNet"],
  [/flow log|network watcher|diagnostic/i, "Monitoring"],
];

function inferResourceType(f: FindingLike): string {
  if (f.resourceType) return f.resourceType;
  const text = `${f.title} ${f.description ?? ""}`;
  for (const [re, label] of RESOURCE_TYPE_PATTERNS) {
    if (re.test(text)) return label;
  }
  return "Other";
}

/** One StatMasterRecord per finding (finding_count = 1). */
export function deriveStatMasters(findings: FindingLike[]): StatMasterRecord[] {
  return findings.map((f) => ({
    traffic_direction: classifyTrafficDirection(f),
    severity: f.severity,
    framework: f.framework ?? "Unmapped",
    region: f.region ?? "Unknown",
    subscription_id: f.credentialId ?? "default",
    resource_type: inferResourceType(f),
    category: f.category || "Uncategorized",
    rule_id: extractRuleId(f.title),
    finding_count: 1,
    resource_count: 1,
    est_monthly_cost_impact: f.estCostImpact ?? 0,
  }));
}
