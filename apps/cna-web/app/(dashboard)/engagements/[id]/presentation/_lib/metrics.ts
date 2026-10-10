// ──────────────────────────────────────────────────────────────────────────────
// Shared utilities for the Presentation site
// All computation is done server-side; these functions are pure / no I/O.
// ──────────────────────────────────────────────────────────────────────────────

export interface Finding {
  id?: string;
  severity: string;
  category: string;
  title: string;
  description: string;
  recommendation: string | null;
  aiGenerated?: boolean;
}

export interface SubnetSummary {
  name: string;
  address_prefix: string;
  nsg_id: string | null;
  nsg_name: string | null;
}

export interface VNetSummary {
  name: string;
  address_space: string[];
  location: string;
  subnets: SubnetSummary[];
}

export interface FirewallSummary {
  name: string;
  sku_tier: string;
  threat_intel_mode: string;
}

export interface NVASummary {
  name: string;
  publisher: string | null;
  offer: string | null;
  identification_method: string;
  nics: { nsg_id: string | null; ip_forwarding_enabled: boolean }[];
}

export interface TopologySub {
  subscription_id: string;
  subscription_name: string | null;
  vnets: VNetSummary[];
  firewalls: FirewallSummary[];
  load_balancers: { name: string; sku_name: string; lb_type: string }[];
  nsgs: { name: string; security_rules: unknown[] }[];
  nvas?: NVASummary[];
  public_ips?: { name: string }[];
  nat_gateways?: { name: string }[];
  private_endpoints?: { name: string }[];
  app_gateways?: { name: string }[];
  express_route_circuits?: { name: string }[];
  route_tables?: { name: string }[];
}

export interface Topology {
  subscriptions: TopologySub[];
}

// ── Risk Scoring ──────────────────────────────────────────────────────────────

const SEV_WEIGHT: Record<string, number> = {
  CRITICAL: 25,
  HIGH: 10,
  MEDIUM: 4,
  LOW: 1,
  INFORMATIONAL: 0,
};

export function computeRiskScore(findings: Finding[]): number {
  const penalty = findings.reduce((sum, f) => sum + (SEV_WEIGHT[f.severity] ?? 0), 0);
  return Math.max(0, Math.min(100, 100 - penalty));
}

export function getRiskLabel(score: number): { label: string; color: string; textClass: string } {
  if (score >= 80) return { label: "Low Risk",      color: "#22c55e", textClass: "text-green-500" };
  if (score >= 60) return { label: "Moderate Risk", color: "#f59e0b", textClass: "text-amber-500" };
  if (score >= 40) return { label: "Elevated Risk", color: "#f97316", textClass: "text-orange-500" };
  return             { label: "Critical Risk", color: "#ef4444", textClass: "text-red-500" };
}

// ── Topology Stats ────────────────────────────────────────────────────────────

export interface TopologyStats {
  subscriptions: number;
  vnets: number;
  subnets: number;
  firewalls: number;
  loadBalancers: number;
  nsgs: number;
  nvas: number;
  publicIps: number;
  privateEndpoints: number;
  natGateways: number;
  appGateways: number;
  expressRoutes: number;
}

export function getTopologyStats(topology: Topology | null): TopologyStats {
  const subs = topology?.subscriptions ?? [];
  return {
    subscriptions:    subs.length,
    vnets:            subs.reduce((n, s) => n + (s.vnets?.length ?? 0), 0),
    subnets:          subs.reduce((n, s) => n + s.vnets.reduce((m, v) => m + (v.subnets?.length ?? 0), 0), 0),
    firewalls:        subs.reduce((n, s) => n + (s.firewalls?.length ?? 0), 0),
    loadBalancers:    subs.reduce((n, s) => n + (s.load_balancers?.length ?? 0), 0),
    nsgs:             subs.reduce((n, s) => n + (s.nsgs?.length ?? 0), 0),
    nvas:             subs.reduce((n, s) => n + ((s.nvas ?? []).length), 0),
    publicIps:        subs.reduce((n, s) => n + ((s.public_ips ?? []).length), 0),
    privateEndpoints: subs.reduce((n, s) => n + ((s.private_endpoints ?? []).length), 0),
    natGateways:      subs.reduce((n, s) => n + ((s.nat_gateways ?? []).length), 0),
    appGateways:      subs.reduce((n, s) => n + ((s.app_gateways ?? []).length), 0),
    expressRoutes:    subs.reduce((n, s) => n + ((s.express_route_circuits ?? []).length), 0),
  };
}

// ── Maturity Dimensions ───────────────────────────────────────────────────────

export interface MaturityDimension {
  label: string;       // short label for radar axis
  fullLabel: string;   // full label for cards
  score: number;       // 1–10
  detail: string;
}

const PLATFORM_SUBNETS = new Set([
  "GatewaySubnet",
  "AzureBastionSubnet",
  "AzureFirewallSubnet",
  "AzureFirewallManagementSubnet",
  "RouteServerSubnet",
]);

function countBySev(findings: Finding[], severities: string[], categories: string[]): number {
  return findings.filter(
    (f) => severities.includes(f.severity) && categories.some((c) => f.category.includes(c)),
  ).length;
}

export function computeMaturityDimensions(
  topology: Topology | null,
  findings: Finding[],
): MaturityDimension[] {
  const subs = topology?.subscriptions ?? [];

  const firewalls     = subs.flatMap((s) => s.firewalls ?? []);
  const allSubnets    = subs.flatMap((s) => s.vnets.flatMap((v) => v.subnets));
  const userSubnets   = allSubnets.filter((s) => !PLATFORM_SUBNETS.has(s.name));
  const protectedSubs = userSubnets.filter((s) => !!s.nsg_id);
  const nsgCoverage   = userSubnets.length > 0 ? protectedSubs.length / userSubnets.length : 0;

  const hasFirewall       = firewalls.length > 0;
  const hasPremiumFW      = firewalls.some((f) => f.sku_tier === "Premium");
  const hasNva            = subs.some((s) => (s.nvas ?? []).length > 0);
  const hasPrivateEps     = subs.some((s) => (s.private_endpoints ?? []).length > 0);
  const hasBastion        = allSubnets.some((s) => s.name === "AzureBastionSubnet");
  const hasAppGw          = subs.some((s) => (s.app_gateways ?? []).length > 0);
  const hasNatGw          = subs.some((s) => (s.nat_gateways ?? []).length > 0);
  const vnetCount         = subs.reduce((n, s) => n + (s.vnets?.length ?? 0), 0);

  // 1. Perimeter Defense
  let perimeter = 4;
  if (hasFirewall) perimeter += 2;
  if (hasPremiumFW) perimeter += 1;
  if (hasNva || hasAppGw) perimeter += 2;
  perimeter -= countBySev(findings, ["CRITICAL"], ["Network Security", "Network Protection"]) * 2;
  perimeter -= countBySev(findings, ["HIGH"], ["Network Security", "Network Protection"]);
  perimeter = Math.max(1, Math.min(10, perimeter));

  // 2. Network Segmentation — primarily driven by NSG coverage
  let segmentation = Math.round(nsgCoverage * 7) + 1; // 1–8 from NSG coverage
  if (vnetCount > 1) segmentation += 1;
  if (subs.some((s) => (s.route_tables ?? []).length > 0)) segmentation += 1;
  segmentation -= countBySev(findings, ["CRITICAL"], ["Network Segmentation"]) * 2;
  segmentation -= countBySev(findings, ["HIGH"], ["Network Segmentation"]);
  segmentation = Math.max(1, Math.min(10, segmentation));

  // 3. Access Control
  let access = 4;
  if (hasPrivateEps) access += 2;
  if (hasBastion) access += 2;
  if (hasNatGw) access += 1;
  access -= countBySev(findings, ["CRITICAL"], ["Access Control"]) * 2;
  access -= countBySev(findings, ["HIGH"], ["Access Control"]);
  access = Math.max(1, Math.min(10, access));

  // 4. Traffic Visibility — penalties from monitoring findings
  const monitorFindings = findings.filter((f) =>
    /(monitor|flow log|diagnostic|watcher|log analytics)/i.test(f.title + " " + f.description),
  );
  let visibility = topology ? 8 : 3;
  visibility -= monitorFindings.filter((f) => f.severity === "CRITICAL").length * 3;
  visibility -= monitorFindings.filter((f) => f.severity === "HIGH").length * 2;
  visibility -= monitorFindings.filter((f) => f.severity === "MEDIUM").length;
  visibility = Math.max(1, Math.min(10, visibility));

  // 5. Compliance Posture
  let compliance = 8;
  compliance -= countBySev(findings, ["CRITICAL"], ["Compliance", "Configuration"]) * 2;
  compliance -= countBySev(findings, ["HIGH"], ["Compliance", "Configuration"]);
  compliance -= countBySev(findings, ["MEDIUM"], ["Compliance", "Configuration"]) * 0.5;
  compliance = Math.max(1, Math.min(10, Math.round(compliance)));

  const accessResources = [
    hasPrivateEps && "Private Endpoints",
    hasBastion    && "Azure Bastion",
    hasNatGw      && "NAT Gateway",
  ].filter(Boolean) as string[];

  const complianceFindings = findings.filter((f) =>
    ["Compliance", "Configuration"].some((c) => f.category.includes(c)),
  );

  return [
    {
      label: "Perimeter",
      fullLabel: "Perimeter Defense",
      score: perimeter,
      detail: hasFirewall
        ? `${firewalls.length} Azure Firewall${firewalls.length !== 1 ? "s" : ""}${hasPremiumFW ? " (Premium)" : ""}${hasNva ? " + NVA/NGFW" : ""}${hasAppGw ? " + App Gateway" : ""}`
        : "No Azure Firewall or NVA detected",
    },
    {
      label: "Segmentation",
      fullLabel: "Network Segmentation",
      score: segmentation,
      detail:
        userSubnets.length > 0
          ? `${Math.round(nsgCoverage * 100)}% of subnets protected by NSG (${protectedSubs.length}/${userSubnets.length})`
          : "No user subnets discovered",
    },
    {
      label: "Access Control",
      fullLabel: "Access Control",
      score: access,
      detail:
        accessResources.length > 0
          ? accessResources.join(", ")
          : "No access control resources detected",
    },
    {
      label: "Visibility",
      fullLabel: "Traffic Visibility",
      score: visibility,
      detail:
        monitorFindings.length === 0
          ? "No monitoring gaps identified"
          : `${monitorFindings.length} monitoring gap${monitorFindings.length !== 1 ? "s" : ""} identified`,
    },
    {
      label: "Compliance",
      fullLabel: "Compliance Posture",
      score: compliance,
      detail:
        complianceFindings.length === 0
          ? "No compliance findings recorded"
          : `${complianceFindings.length} compliance finding${complianceFindings.length !== 1 ? "s" : ""}`,
    },
  ];
}

// ── Remediation Plan ──────────────────────────────────────────────────────────

export interface RemediationItem {
  title: string;
  recommendation: string;
  severity: string;
  category: string;
}

export interface RemediationPhase {
  phase: number;
  label: string;
  timeframe: string;
  phaseColor: string;
  items: RemediationItem[];
}

export function buildRemediationPlan(findings: Finding[]): RemediationPhase[] {
  const bySev = (sev: string) =>
    findings
      .filter((f) => f.severity === sev)
      .map((f) => ({
        title: f.title,
        recommendation: f.recommendation ?? "Remediate as soon as possible.",
        severity: f.severity,
        category: f.category,
      }));

  const phases: RemediationPhase[] = [
    {
      phase: 1,
      label: "Immediate Action",
      timeframe: "0–30 days",
      phaseColor: "text-red-500",
      items: bySev("CRITICAL"),
    },
    {
      phase: 2,
      label: "Short-Term Remediation",
      timeframe: "30–90 days",
      phaseColor: "text-orange-500",
      items: bySev("HIGH"),
    },
    {
      phase: 3,
      label: "Medium-Term Improvements",
      timeframe: "90–180 days",
      phaseColor: "text-amber-500",
      items: [...bySev("MEDIUM"), ...bySev("LOW")],
    },
  ];

  return phases.filter((p) => p.items.length > 0);
}

// ── Severity Helpers ──────────────────────────────────────────────────────────

export const SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"] as const;
export type Sev = (typeof SEV_ORDER)[number];

export const SEV_COLORS: Record<Sev, { bar: string; text: string; bg: string; badge: string; hex: string }> = {
  CRITICAL:      { bar: "bg-red-500",    text: "text-red-600 dark:text-red-400",       bg: "border-red-200 bg-red-50/60 dark:border-red-800/40 dark:bg-red-900/10",          badge: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",    hex: "#ef4444" },
  HIGH:          { bar: "bg-orange-500", text: "text-orange-600 dark:text-orange-400", bg: "border-orange-200 bg-orange-50/60 dark:border-orange-800/40 dark:bg-orange-900/10", badge: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400", hex: "#f97316" },
  MEDIUM:        { bar: "bg-amber-400",  text: "text-amber-600 dark:text-amber-400",   bg: "border-amber-200 bg-amber-50/60 dark:border-amber-800/40 dark:bg-amber-900/10",   badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",   hex: "#f59e0b" },
  LOW:           { bar: "bg-blue-400",   text: "text-blue-600 dark:text-blue-400",     bg: "border-blue-200 bg-blue-50/60 dark:border-blue-800/40 dark:bg-blue-900/10",       badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",     hex: "#60a5fa" },
  INFORMATIONAL: { bar: "bg-navy-300",   text: "text-navy-500 dark:text-navy-300",     bg: "border-navy-100 bg-navy-50/60 dark:border-navy-700/40 dark:bg-navy-800/20",       badge: "bg-navy-100 text-navy-500 dark:bg-navy-700/40 dark:text-navy-300",     hex: "#64748b" },
};
