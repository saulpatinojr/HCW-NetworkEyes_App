// ──────────────────────────────────────────────────────────────────────────────
// Section skeleton + data slicing for the sectioned Comprehensive Assessment.
// Each section declares a charter (what it must cover) and a slice() that
// returns ONLY the engagement data relevant to that section — the model never
// sees data it shouldn't ground on, and per-call context stays small.
// ──────────────────────────────────────────────────────────────────────────────

import { classifyTrafficDirection, type FindingLike } from "@/lib/derive-stat-masters";

export interface ReportFinding extends FindingLike {
  id: string;
  recommendation?: string | null;
  aiGenerated?: boolean;
}

export interface SectionInput {
  clientOrg: string;
  engagementName: string;
  findings: ReportFinding[];
  /** Merged multi-subscription topology JSON (raw string) */
  topologyJson?: string | null;
  /** Pre-rendered full topology summary (from openai.ts summarizeTopology) */
  topologySummary?: string | null;
  credentialsInfo?: Array<{
    label: string;
    platform: string;
    tenantId: string | null;
    subscriptionIds: string[];
  }>;
  documents?: { fileName: string; text: string }[];
}

export interface SectionSpec {
  id: string;
  number: number;
  title: string;
  /** What the section must cover — becomes charter bullets in the prompt. */
  charter: string[];
  maxCompletionTokens: number;
  /**
   * Return the data slice for this section, or null when the engagement has
   * no data for the domain (the orchestrator then emits a deterministic stub
   * instead of spending an AI call).
   */
  slice(input: SectionInput): string | null;
}

// ── Finding formatters ────────────────────────────────────────────────────────

const MAX_SLICE_CHARS = 40_000; // ~10k tokens ceiling per section context

function formatFindings(findings: ReportFinding[], heading: string): string | null {
  if (!findings.length) return null;
  const lines = [`=== ${heading} (${findings.length}) ===`];
  for (const f of findings) {
    lines.push(`Finding: ${f.title}`);
    lines.push(`  Severity: ${f.severity} | Category: ${f.category}`);
    if (f.region) lines.push(`  Region: ${f.region}`);
    if (f.resourceType) lines.push(`  Resource type: ${f.resourceType}`);
    if (typeof f.estCostImpact === "number" && f.estCostImpact > 0) {
      lines.push(`  Est. monthly cost impact: $${f.estCostImpact} [VERIFY]`);
    }
    if (f.description) lines.push(`  Description: ${f.description}`);
    if (f.recommendation) lines.push(`  Recommendation: ${f.recommendation}`);
  }
  return lines.join("\n").slice(0, MAX_SLICE_CHARS);
}

function byDirection(findings: ReportFinding[], dir: string): ReportFinding[] {
  return findings.filter((f) => classifyTrafficDirection(f) === dir);
}

function byPattern(findings: ReportFinding[], re: RegExp): ReportFinding[] {
  return findings.filter((f) => re.test(`${f.title} ${f.category} ${f.description ?? ""}`));
}

const ROUTING_RE = /\b(rout|udr|bgp|next.hop|expressroute|express route|vpn|peering|transit|black.?hole|prefix)\b/i;
const MONITORING_RE = /\b(log|monitor|observab|diagnostic|flow log|network watcher|alert|siem|audit|retention)\b/i;
const RESILIENCE_RE = /\b(resilien|availab|redundan|zone|sla|failover|single point|spof|health probe|active.active|ddos)\b/i;
const IDENTITY_RE = /\b(identity|rbac|role.based|privileg|bastion|jit|management plane|admin|credential|service principal|managed identity)\b/i;
const COST_RE = /\bcost|finops|optimi[sz]ation|spend|orphan|idle|unused|oversized\b/i;
const FRAMEWORK_RE = /\b(NIST\s?(SP\s?800-53)?[\s-]*[A-Z]{2}-\d+|CIS\s?(Azure|Controls?)?\s?v?\d+(\.\d+)*|ISO\s?27001|SOC\s?2|HIPAA|PCI[\s-]?DSS|Zero Trust|Well-Architected)\b/i;

// ── Topology extractors ───────────────────────────────────────────────────────
// Pure functions over the parsed topology JSON — each returns a compact text
// extract for one domain, mirroring the style of summarizeTopology().

type Topo = { subscriptions?: Array<Record<string, unknown>> };

function parseTopo(topologyJson?: string | null): Topo | null {
  if (!topologyJson) return null;
  try {
    return JSON.parse(topologyJson) as Topo;
  } catch {
    return null;
  }
}

function subName(sub: Record<string, unknown>): string {
  return String(sub.subscription_name ?? sub.subscription_id ?? "unknown");
}

function arr(sub: Record<string, unknown>, key: string): Array<Record<string, unknown>> {
  return (sub[key] as Array<Record<string, unknown>> | undefined) ?? [];
}

export function extractPerimeter(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines = ["=== PERIMETER TOPOLOGY EXTRACT ==="];
  for (const sub of topo.subscriptions) {
    lines.push(`Subscription: ${subName(sub)}`);
    const fws = arr(sub, "firewalls");
    lines.push(fws.length ? `  Azure Firewalls (${fws.length}):` : "  Azure Firewalls: NONE DEPLOYED");
    for (const fw of fws) {
      lines.push(`    - ${fw.name} sku=${fw.sku_tier} threatIntel=${fw.threat_intel_mode} zones=${((fw.zones as string[]) ?? []).join(",") || "none"}`);
    }
    for (const agw of arr(sub, "application_gateways")) {
      lines.push(`  AppGW: ${agw.name} sku=${agw.sku_name} waf=${agw.waf_enabled} wafMode=${agw.waf_mode ?? "N/A"}`);
    }
    const pips = arr(sub, "public_ips");
    const unassoc = pips.filter((p) => !p.associated_resource_id);
    lines.push(`  Public IPs: ${pips.length} total, ${unassoc.length} unassociated`);
    for (const pip of pips) {
      lines.push(`    - ${pip.name} ${pip.ip_address ?? "dynamic"} assoc=${pip.associated_resource_type ?? "UNASSOCIATED"}`);
    }
    for (const gw of arr(sub, "virtual_network_gateways")) {
      lines.push(`  Gateway: ${gw.name} type=${gw.gateway_type} sku=${gw.sku_name} activeActive=${gw.active_active}`);
    }
    for (const lb of arr(sub, "load_balancers")) {
      lines.push(`  LB: ${lb.name} sku=${lb.sku_name} type=${lb.lb_type} zones=${((lb.zones as string[]) ?? []).join(",") || "none"}`);
    }
    for (const b of arr(sub, "bastion_hosts")) {
      lines.push(`  Bastion: ${b.name} sku=${b.sku_name}`);
    }
    for (const ng of arr(sub, "nat_gateways")) {
      lines.push(`  NAT GW: ${ng.name} pips=${(ng.public_ip_ids as string[] | undefined)?.length ?? 0}`);
    }
  }
  return lines.join("\n").slice(0, MAX_SLICE_CHARS);
}

export function extractSegmentation(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines = ["=== SEGMENTATION TOPOLOGY EXTRACT ==="];
  for (const sub of topo.subscriptions) {
    lines.push(`Subscription: ${subName(sub)}`);
    for (const v of arr(sub, "vnets")) {
      lines.push(`  VNet ${v.name} [${((v.address_space as string[]) ?? []).join(", ")}]`);
      for (const s of (v.subnets as Array<Record<string, unknown>> | undefined) ?? []) {
        lines.push(`    Subnet ${s.name} ${s.address_prefix} NSG=${s.nsg_name ?? "NONE"} UDR=${s.route_table_name ?? "none"}`);
      }
      for (const p of (v.peerings as Array<Record<string, unknown>> | undefined) ?? []) {
        lines.push(`    Peering ${p.name} → ${p.remote_vnet_name ?? p.remote_vnet_id} state=${p.peering_state} gwTransit=${p.allow_gateway_transit} fwdTraffic=${p.allow_forwarded_traffic ?? "?"}`);
      }
    }
    for (const nsg of arr(sub, "nsgs")) {
      const rules = (nsg.security_rules as Array<Record<string, unknown>> | undefined) ?? [];
      lines.push(`  NSG ${nsg.name} subnets=${(nsg.associated_subnet_ids as string[] | undefined)?.length ?? 0} rules=${rules.length}`);
      for (const r of rules.slice(0, 15)) {
        const src = r.source_address_prefix ?? ((r.source_address_prefixes as string[]) ?? []).join(",");
        const dst = r.destination_address_prefix ?? ((r.destination_address_prefixes as string[]) ?? []).join(",");
        const port = r.destination_port_range ?? ((r.destination_port_ranges as string[]) ?? []).join(",");
        lines.push(`    [${r.priority}] ${r.direction} ${r.access} ${r.protocol} src=${src} dst=${dst} port=${port}`);
      }
      if (rules.length > 15) lines.push(`    ... ${rules.length - 15} more rules`);
    }
  }
  return lines.join("\n").slice(0, MAX_SLICE_CHARS);
}

export function extractRouting(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines = ["=== ROUTING & CONNECTIVITY TOPOLOGY EXTRACT ==="];
  for (const sub of topo.subscriptions) {
    lines.push(`Subscription: ${subName(sub)}`);
    for (const rt of arr(sub, "route_tables")) {
      lines.push(`  Route Table ${rt.name} subnets=${(rt.associated_subnet_ids as string[] | undefined)?.length ?? 0} bgpPropagation=${!rt.disable_bgp_route_propagation}`);
      for (const r of (rt.routes as Array<Record<string, unknown>> | undefined) ?? []) {
        lines.push(`    ${r.name}: ${r.address_prefix} → ${r.next_hop_type}${r.next_hop_ip ? ` (${r.next_hop_ip})` : ""}`);
      }
    }
    for (const gw of arr(sub, "virtual_network_gateways")) {
      lines.push(`  Gateway ${gw.name} type=${gw.gateway_type} bgp=${gw.enable_bgp} asn=${gw.bgp_asn ?? "N/A"}`);
      for (const c of (gw.connections as Array<Record<string, unknown>> | undefined) ?? []) {
        lines.push(`    Conn ${c.name} type=${c.connection_type} status=${c.connection_status} bgp=${c.enable_bgp}`);
      }
    }
    for (const er of arr(sub, "express_route_circuits")) {
      lines.push(`  ExpressRoute ${er.name} provider=${er.service_provider ?? "?"} bw=${er.bandwidth_mbps ?? "?"}Mbps globalReach=${er.global_reach_enabled}`);
    }
    for (const z of arr(sub, "private_dns_zones")) {
      lines.push(`  Private DNS ${z.name} linkedVnets=${(z.linked_vnet_ids as string[] | undefined)?.length ?? 0} autoReg=${z.auto_registration_enabled}`);
    }
    for (const ng of arr(sub, "nat_gateways")) {
      lines.push(`  NAT GW ${ng.name} subnets=${(ng.associated_subnet_ids as string[] | undefined)?.length ?? 0}`);
    }
  }
  return lines.join("\n").slice(0, MAX_SLICE_CHARS);
}

export function extractManagementPlane(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines = ["=== MANAGEMENT PLANE TOPOLOGY EXTRACT ==="];
  for (const sub of topo.subscriptions) {
    lines.push(`Subscription: ${subName(sub)}`);
    const bastions = arr(sub, "bastion_hosts");
    lines.push(bastions.length ? `  Bastion Hosts (${bastions.length}):` : "  Bastion Hosts: NONE DEPLOYED");
    for (const b of bastions) {
      lines.push(`    - ${b.name} sku=${b.sku_name} tunneling=${b.tunneling_enabled} shareableLink=${b.shareable_link_enabled}`);
    }
    for (const pe of arr(sub, "private_endpoints")) {
      lines.push(`  Private Endpoint ${pe.name} subnet=${String(pe.subnet_id ?? "").split("/").slice(-1)[0]}`);
    }
  }
  return lines.join("\n").slice(0, MAX_SLICE_CHARS);
}

export function extractResilience(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines = ["=== RESILIENCE TOPOLOGY EXTRACT ==="];
  for (const sub of topo.subscriptions) {
    lines.push(`Subscription: ${subName(sub)}`);
    for (const lb of arr(sub, "load_balancers")) {
      lines.push(`  LB ${lb.name} sku=${lb.sku_name} probes=${(lb.probes as unknown[] | undefined)?.length ?? 0} zones=${((lb.zones as string[]) ?? []).join(",") || "NONE"}`);
    }
    for (const gw of arr(sub, "virtual_network_gateways")) {
      lines.push(`  Gateway ${gw.name} sku=${gw.sku_name} activeActive=${gw.active_active}`);
    }
    for (const fw of arr(sub, "firewalls")) {
      lines.push(`  Firewall ${fw.name} zones=${((fw.zones as string[]) ?? []).join(",") || "NONE"}`);
    }
    for (const v of arr(sub, "vnets")) {
      lines.push(`  VNet ${v.name} DDoS=${v.ddos_protection_enabled ? "enabled" : "NOT ENABLED"}`);
    }
  }
  return lines.join("\n").slice(0, MAX_SLICE_CHARS);
}

// ── Live telemetry extractors (v1.3 discovery aggregates) ─────────────────────
// Discovery collects 24h Azure Monitor metrics, Traffic Analytics volumes,
// Defender assessments, and observability coverage. Surfacing them is what
// turns "you have 3 gateways" into "your ER primary ran at 74% yesterday".

function fmtBytes(b: number): string {
  if (b >= 1e12) return `${(b / 1e12).toFixed(1)} TB`;
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  return `${Math.round(b)} B`;
}

function pct(v: unknown): string {
  return typeof v === "number" ? `${v.toFixed(1)}%` : "n/a";
}

function metrics(sub: Record<string, unknown>): Record<string, unknown> | null {
  return (sub.network_metrics as Record<string, unknown> | undefined) ?? null;
}

/** Real traffic volumes + address-space utilization — feeds Architecture. */
export function extractLiveTraffic(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines: string[] = [];
  for (const sub of topo.subscriptions) {
    const m = metrics(sub);
    if (!m) continue;
    const parts: string[] = [];
    if (typeof m.nta_east_west_bytes_24h === "number") {
      parts.push(`east-west traffic (24h): ${fmtBytes(m.nta_east_west_bytes_24h)} [VERIFY]`);
    }
    if (typeof m.nta_north_south_bytes_24h === "number") {
      parts.push(`north-south traffic (24h): ${fmtBytes(m.nta_north_south_bytes_24h)} [VERIFY]`);
    }
    const util = (m.vnet_utilization as Record<string, number> | undefined) ?? {};
    for (const [vnetId, u] of Object.entries(util)) {
      parts.push(`address-space utilization ${vnetId.split("/").slice(-1)[0]}: ${u.toFixed(1)}%`);
    }
    if (parts.length) {
      lines.push(`Subscription ${subName(sub)}:`);
      for (const p of parts) lines.push(`  - ${p}`);
    }
  }
  return lines.length ? ["=== MEASURED TRAFFIC & UTILIZATION (Azure Monitor / Traffic Analytics, 24h) ===", ...lines].join("\n") : null;
}

/** Firewall/AppGW/DDoS/WAF/NVA telemetry — feeds Perimeter. */
export function extractPerimeterTelemetry(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines: string[] = [];
  for (const sub of topo.subscriptions) {
    const subLines: string[] = [];
    const m = metrics(sub);
    if (m) {
      for (const fw of (m.firewall_metrics as Array<Record<string, unknown>> | undefined) ?? []) {
        subLines.push(`Firewall ${fw.firewall_name} (24h): ${typeof fw.data_processed_gb_24h === "number" ? `${(fw.data_processed_gb_24h as number).toFixed(1)} GB processed` : "no data"}, rule hits app=${fw.app_rule_hits_24h ?? "n/a"} net=${fw.network_rule_hits_24h ?? "n/a"} nat=${fw.nat_rule_hits_24h ?? "n/a"}`);
      }
      for (const ag of (m.appgw_metrics as Array<Record<string, unknown>> | undefined) ?? []) {
        subLines.push(`AppGW ${ag.appgw_name} (24h): requests=${ag.total_requests_24h ?? "n/a"} failed=${ag.failed_requests_24h ?? "n/a"} backendLatency=${ag.backend_latency_ms_avg ?? "n/a"}ms WAF hits=${ag.waf_rule_hits_24h ?? "n/a"}`);
      }
      const ddos = m.ddos_attack_events_24h;
      if (typeof ddos === "number" && ddos > 0) {
        subLines.push(`DDoS ATTACK EVENTS (24h): ${ddos} — public IPs under attack: ${((m.public_ips_under_ddos_attack as string[]) ?? []).join(", ")}`);
      }
    }
    for (const p of arr(sub, "front_door_waf_policies")) {
      subLines.push(`Front Door WAF policy ${p.name}: mode=${p.policy_mode} state=${p.policy_enabled_state} customRules=${p.custom_rules_count} managedRules=${p.managed_rules_count}`);
    }
    for (const nva of arr(sub, "nvas")) {
      subLines.push(`NVA ${nva.name}: vendor=${nva.publisher ?? "unknown"} offer=${nva.offer ?? "?"} identifiedBy=${nva.identification_method} nics=${(nva.nics as unknown[] | undefined)?.length ?? 0}`);
    }
    if (subLines.length) {
      lines.push(`Subscription ${subName(sub)}:`);
      for (const l of subLines) lines.push(`  - ${l}`);
    }
  }
  return lines.length ? ["=== PERIMETER TELEMETRY (measured, 24h window) ===", ...lines].join("\n") : null;
}

/** Flow-log / diagnostics / alerting coverage — feeds Observability. */
export function extractObservabilityPosture(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines: string[] = [];
  for (const sub of topo.subscriptions) {
    const o = sub.observability as Record<string, unknown> | undefined;
    if (!o) continue;
    lines.push(`Subscription ${subName(sub)}:`);
    lines.push(`  - NSG flow logs: ${o.nsg_flow_logs_enabled ?? 0}/${o.nsg_flow_logs_total ?? 0} NSGs enabled; Traffic Analytics on ${o.traffic_analytics_enabled ?? 0} of them`);
    lines.push(`  - Diagnostics to Log Analytics: gateways ${o.gateways_with_diagnostics ?? 0}/${o.gateways_total ?? 0}, firewalls ${o.firewalls_with_diagnostics ?? 0}/${o.firewalls_total ?? 0}, AppGW ${o.appgw_with_diagnostics ?? 0}/${o.appgw_total ?? 0}, LB ${o.lb_with_diagnostics ?? 0}/${o.lb_total ?? 0}, bastion ${o.bastion_with_diagnostics ?? 0}/${o.bastion_total ?? 0}`);
    lines.push(`  - Alert rules: ${o.metric_alert_count ?? 0} metric alerts, ${o.activity_log_alert_count ?? 0} activity-log alerts (subscription-wide)`);
    const workspaces = (o.log_analytics_workspaces as Array<Record<string, unknown>> | undefined) ?? [];
    for (const w of workspaces) {
      lines.push(`  - Log Analytics workspace ${w.name}: retention=${w.retention_days ?? "?"}d sku=${w.sku ?? "?"}`);
    }
    const watchers = (o.network_watchers as Array<Record<string, unknown>> | undefined) ?? [];
    lines.push(`  - Network Watchers: ${watchers.length} (${watchers.map((w) => w.location).join(", ") || "none"})`);
  }
  return lines.length ? ["=== OBSERVABILITY COVERAGE (measured) ===", ...lines].join("\n") : null;
}

/** Gateway/ER/SNAT utilization — capacity headroom evidence for Resilience. */
export function extractUtilizationTelemetry(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines: string[] = [];
  for (const sub of topo.subscriptions) {
    const m = metrics(sub);
    if (!m) continue;
    const subLines: string[] = [];
    for (const g of (m.gateway_metrics as Array<Record<string, unknown>> | undefined) ?? []) {
      subLines.push(`Gateway ${g.gateway_name} (${g.gateway_type}): utilization=${pct(g.utilization_pct)} of ${g.bandwidth_mbps_provisioned ?? "?"} Mbps, in=${typeof g.ingress_bytes_24h === "number" ? fmtBytes(g.ingress_bytes_24h as number) : "n/a"}/24h out=${typeof g.egress_bytes_24h === "number" ? fmtBytes(g.egress_bytes_24h as number) : "n/a"}/24h`);
    }
    for (const er of (m.er_circuit_metrics as Array<Record<string, unknown>> | undefined) ?? []) {
      subLines.push(`ER circuit ${er.circuit_name}: primary=${pct(er.primary_utilization_pct)} secondary=${pct(er.secondary_utilization_pct)} of ${er.bandwidth_mbps_provisioned ?? "?"} Mbps`);
    }
    for (const lb of (m.lb_metrics as Array<Record<string, unknown>> | undefined) ?? []) {
      subLines.push(`LB ${lb.lb_name}: SNAT port utilization=${pct(lb.snat_port_utilization_pct)} (used ${lb.used_snat_ports ?? "?"}/${lb.allocated_snat_ports ?? "?"})`);
    }
    if (subLines.length) {
      lines.push(`Subscription ${subName(sub)}:`);
      for (const l of subLines) lines.push(`  - ${l}`);
    }
  }
  return lines.length ? ["=== CAPACITY & UTILIZATION TELEMETRY (Azure Monitor, 24h) — all figures [VERIFY] ===", ...lines].join("\n") : null;
}

/** BGP peers/routes, Route Servers, vWAN — transit evidence for Routing. */
export function extractBgpAndTransit(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines: string[] = [];
  for (const sub of topo.subscriptions) {
    const subLines: string[] = [];
    for (const g of arr(sub, "bgp_data")) {
      if (!g.bgp_enabled) continue;
      subLines.push(`Gateway ${g.gateway_name}: ASN=${g.bgp_asn ?? "?"} learned=${g.learned_routes_count ?? 0} routes advertised=${g.advertised_routes_count ?? 0}`);
      for (const p of (g.peers as Array<Record<string, unknown>> | undefined) ?? []) {
        subLines.push(`  peer ${p.peer_ip} (ASN ${p.peer_asn ?? "?"}): state=${p.state} routesReceived=${p.routes_received ?? 0}`);
      }
      const learned = ((g.learned_routes as string[]) ?? []).slice(0, 12);
      if (learned.length) subLines.push(`  learned prefixes (sample): ${learned.join(", ")}`);
    }
    for (const rs of arr(sub, "route_servers")) {
      subLines.push(`Route Server ${rs.name}: branch-to-branch=${rs.branch_to_branch ?? "?"} bgpConnections=${(rs.bgp_connections as unknown[] | undefined)?.length ?? 0}`);
    }
    for (const vw of arr(sub, "virtual_wans")) {
      subLines.push(`Virtual WAN ${vw.name}: hubs=${(vw.hubs as unknown[] | undefined)?.length ?? 0}`);
    }
    if (subLines.length) {
      lines.push(`Subscription ${subName(sub)}:`);
      for (const l of subLines) lines.push(`  - ${l}`);
    }
  }
  return lines.length ? ["=== BGP & TRANSIT STATE (Network Watcher, live) ===", ...lines].join("\n") : null;
}

/** Unhealthy Defender for Cloud networking assessments — feeds Compliance. */
export function extractDefenderPosture(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines: string[] = [];
  for (const sub of topo.subscriptions) {
    const assessments = arr(sub, "defender_assessments");
    if (!assessments.length) continue;
    lines.push(`Subscription ${subName(sub)} — ${assessments.length} unhealthy Defender assessment(s):`);
    for (const a of assessments.slice(0, 40)) {
      const resource = typeof a.resource_id === "string" ? a.resource_id.split("/").slice(-1)[0] : "?";
      lines.push(`  - [${a.severity}] ${a.display_name} (resource: ${resource}${a.implementation_effort ? `, effort: ${a.implementation_effort}` : ""})`);
    }
    if (assessments.length > 40) lines.push(`  ... ${assessments.length - 40} more`);
  }
  return lines.length ? ["=== MICROSOFT DEFENDER FOR CLOUD — NETWORK ASSESSMENTS (live) ===", ...lines].join("\n") : null;
}

/** Real MTD network egress spend — feeds FinOps. */
export function extractEgressCost(topologyJson?: string | null): string | null {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return null;
  const lines: string[] = [];
  for (const sub of topo.subscriptions) {
    const m = metrics(sub);
    const cost = m?.egress_cost_usd_mtd;
    if (typeof cost === "number") {
      lines.push(`Subscription ${subName(sub)}: $${cost.toFixed(2)} network egress spend month-to-date (Azure Cost Management, actual)`);
    }
  }
  return lines.length ? ["=== MEASURED NETWORK EGRESS SPEND (Cost Management, actual MTD) ===", ...lines].join("\n") : null;
}

// ── Inventory counts (used by scope section and Appendix B) ──────────────────

const INVENTORY_KEYS: Array<[string, string]> = [
  ["vnets", "Virtual Networks"],
  ["nsgs", "Network Security Groups"],
  ["route_tables", "Route Tables"],
  ["virtual_network_gateways", "VNet Gateways"],
  ["load_balancers", "Load Balancers"],
  ["firewalls", "Azure Firewalls"],
  ["application_gateways", "Application Gateways"],
  ["public_ips", "Public IPs"],
  ["private_endpoints", "Private Endpoints"],
  ["nat_gateways", "NAT Gateways"],
  ["bastion_hosts", "Bastion Hosts"],
  ["express_route_circuits", "ExpressRoute Circuits"],
  ["private_dns_zones", "Private DNS Zones"],
];

export interface InventoryRow {
  subscription: string;
  counts: Array<{ label: string; count: number }>;
}

export function inventoryCounts(topologyJson?: string | null): InventoryRow[] {
  const topo = parseTopo(topologyJson);
  if (!topo?.subscriptions?.length) return [];
  return topo.subscriptions.map((sub) => ({
    subscription: subName(sub),
    counts: INVENTORY_KEYS.map(([key, label]) => ({ label, count: arr(sub, key).length })),
  }));
}

// ── Environment snapshot ──────────────────────────────────────────────────────
// A deterministic, compact picture of the WHOLE estate, injected into every
// section call. Sections run in parallel and can't see each other's prose;
// this shared snapshot is what lets twelve independent calls tell one story
// about one network instead of twelve disconnected essays.

export function buildEnvironmentSnapshot(input: SectionInput): string {
  const lines = ["=== ENVIRONMENT SNAPSHOT (shared context — the whole estate at a glance) ==="];
  lines.push(`Client: ${input.clientOrg} | Engagement: ${input.engagementName}`);

  const inv = inventoryCounts(input.topologyJson);
  for (const row of inv) {
    const nonZero = row.counts.filter((c) => c.count > 0);
    lines.push(`Subscription "${row.subscription}": ${nonZero.map((c) => `${c.count} ${c.label}`).join(", ") || "no network resources discovered"}`);
  }

  lines.push(`Findings: ${input.findings.length} total — ${severityBreakdown(input.findings) || "none"}`);

  // Top categories by finding volume — where the pain concentrates.
  const byCategory = new Map<string, number>();
  for (const f of input.findings) byCategory.set(f.category, (byCategory.get(f.category) ?? 0) + 1);
  const topCats = [...byCategory.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  if (topCats.length) {
    lines.push(`Finding concentration: ${topCats.map(([c, n]) => `${c} (${n})`).join(", ")}`);
  }

  // Traffic-direction spread — the shape of the risk.
  const dirs = { north_south: 0, east_west: 0, management: 0, unclassified: 0 };
  for (const f of input.findings) dirs[classifyTrafficDirection(f)]++;
  lines.push(`Risk by traffic plane: ${dirs.north_south} north-south, ${dirs.east_west} east-west, ${dirs.management} management-plane, ${dirs.unclassified} unclassified`);

  // Posture signals an SME reads first.
  const topo = parseTopo(input.topologyJson);
  if (topo?.subscriptions?.length) {
    const signals: string[] = [];
    let fwCount = 0, ddosVnets = 0, vnetCount = 0, nakedSubnets = 0, subnetCount = 0;
    for (const sub of topo.subscriptions) {
      fwCount += arr(sub, "firewalls").length;
      for (const v of arr(sub, "vnets")) {
        vnetCount++;
        if (v.ddos_protection_enabled) ddosVnets++;
        for (const s of (v.subnets as Array<Record<string, unknown>> | undefined) ?? []) {
          subnetCount++;
          if (!s.nsg_name) nakedSubnets++;
        }
      }
    }
    signals.push(fwCount === 0 ? "NO centralized firewall deployed" : `${fwCount} Azure Firewall(s)`);
    signals.push(`${nakedSubnets}/${subnetCount} subnets without an NSG`);
    signals.push(`${ddosVnets}/${vnetCount} VNets with DDoS protection`);
    lines.push(`Posture signals: ${signals.join("; ")}`);
  }

  const costTotal = input.findings.reduce((s, f) => s + (typeof f.estCostImpact === "number" ? f.estCostImpact : 0), 0);
  if (costTotal > 0) {
    lines.push(`Estimated monthly cost waste identified: $${Math.round(costTotal)} [VERIFY]`);
  }

  return lines.join("\n");
}

// ── Section skeleton ──────────────────────────────────────────────────────────

function severityBreakdown(findings: ReportFinding[]): string {
  const order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"];
  return order
    .map((s) => ({ s, n: findings.filter((f) => f.severity === s).length }))
    .filter((x) => x.n > 0)
    .map((x) => `${x.n} ${x.s}`)
    .join(", ");
}

export const COMPREHENSIVE_SECTIONS: SectionSpec[] = [
  // Section 1 (Executive Summary) is produced by the synthesis pass — not here.
  {
    id: "scope",
    number: 2,
    title: "Scope & Methodology",
    charter: [
      "Assessed cloud scope: tenants, subscriptions, and credentials used",
      "Discovery methodology: live Azure Resource Manager discovery plus rule-based and AI-assisted analysis",
      "Documents reviewed and their role in the assessment",
      "Explicit statement of what was NOT assessed (data limitations, blocked subscriptions)",
    ],
    maxCompletionTokens: 3000,
    slice(input) {
      const lines = ["=== SCOPE DATA ==="];
      for (const c of input.credentialsInfo ?? []) {
        lines.push(`Credential: [${c.platform}] ${c.label} tenant=${c.tenantId ?? "N/A"} subscriptions=${c.subscriptionIds.join(", ") || "all accessible"}`);
      }
      lines.push(`Total findings: ${input.findings.length} (${severityBreakdown(input.findings)})`);
      lines.push(`Live-discovery findings: ${input.findings.filter((f) => !f.aiGenerated).length}; AI-analysis findings: ${input.findings.filter((f) => f.aiGenerated).length}`);
      const inv = inventoryCounts(input.topologyJson);
      for (const row of inv) {
        lines.push(`Subscription "${row.subscription}": ${row.counts.filter((c) => c.count > 0).map((c) => `${c.count} ${c.label}`).join(", ")}`);
      }
      if (input.documents?.length) {
        lines.push(`Documents reviewed: ${input.documents.map((d) => d.fileName).join("; ")}`);
      }
      return lines.join("\n");
    },
  },
  {
    id: "architecture",
    number: 3,
    title: "Architecture & Topology Analysis",
    charter: [
      "Describe the discovered network architecture: hub/spoke or flat, address space plan, regions",
      "Traffic flow narrative: how north-south and east-west traffic actually moves today — anchor it in the MEASURED 24h traffic volumes when present",
      "Address-space utilization: which VNets are running out of room, which are over-allocated",
      "Dependency mapping: shared services, transit paths, single points of failure at the architecture level",
      "An ASCII/Unicode logical topology diagram of the discovered environment",
      "Architecture-level observations that individual findings do not capture",
    ],
    maxCompletionTokens: 6000,
    slice(input) {
      const t = input.topologySummary;
      const live = extractLiveTraffic(input.topologyJson);
      if (!t && !live) return null;
      return [t, live].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "perimeter",
    number: 4,
    title: "Perimeter Security (North–South)",
    charter: [
      "Internet exposure surface: public IPs, exposed services, ingress paths",
      "Perimeter inspection posture: firewall coverage, WAF (including Front Door policies and their Detection/Prevention mode), DDoS protection — and whether the MEASURED telemetry shows the controls actually working (rule hits, WAF matches, attack events)",
      "Third-party NVAs discovered in the estate and how they fit the inspection story",
      "Egress control: outbound paths, NAT, forced tunneling",
      "Each relevant finding analyzed in depth with concrete Azure remediation steps",
    ],
    maxCompletionTokens: 6000,
    slice(input) {
      const f = formatFindings(byDirection(input.findings, "north_south"), "NORTH-SOUTH FINDINGS");
      const t = extractPerimeter(input.topologyJson);
      const telemetry = extractPerimeterTelemetry(input.topologyJson);
      if (!f && !t && !telemetry) return null;
      return [f, t, telemetry].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "segmentation",
    number: 5,
    title: "Network Segmentation (East–West)",
    charter: [
      "Segmentation model: VNet/subnet isolation, NSG coverage and rule quality",
      "Lateral movement paths: peering mesh, permissive intra-VNet rules, missing micro-segmentation",
      "Zero Trust alignment of the current segmentation design",
      "Each relevant finding analyzed in depth with concrete Azure remediation steps",
    ],
    maxCompletionTokens: 6000,
    slice(input) {
      const f = formatFindings(byDirection(input.findings, "east_west"), "EAST-WEST FINDINGS");
      const t = extractSegmentation(input.topologyJson);
      if (!f && !t) return null;
      return [f, t].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "routing",
    number: 6,
    title: "Routing & Connectivity",
    charter: [
      "UDR posture: routes overriding system routing, next-hop safety, inspection bypass risk",
      "Hybrid connectivity: ExpressRoute/VPN design, BGP scope, redundancy — read the LIVE BGP peer states and learned/advertised route counts when present",
      "Transit fabric: Route Server, Virtual WAN hubs, and what they imply for route propagation",
      "DNS architecture: private zones, resolution paths, auto-registration",
      "Each relevant finding analyzed in depth with concrete Azure remediation steps",
    ],
    maxCompletionTokens: 5000,
    slice(input) {
      const f = formatFindings(byPattern(input.findings, ROUTING_RE), "ROUTING FINDINGS");
      const t = extractRouting(input.topologyJson);
      const bgp = extractBgpAndTransit(input.topologyJson);
      if (!f && !t && !bgp) return null;
      return [f, t, bgp].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "management",
    number: 7,
    title: "Identity & Management Plane",
    charter: [
      "Administrative access paths: Bastion coverage, exposed management ports, JIT",
      "Network-plane RBAC and privileged access observations",
      "Private endpoint adoption for management-plane traffic",
      "Each relevant finding analyzed in depth with concrete Azure remediation steps",
    ],
    maxCompletionTokens: 5000,
    slice(input) {
      const mgmt = new Set(byDirection(input.findings, "management").map((f) => f.title));
      const idFindings = input.findings.filter(
        (f) => mgmt.has(f.title) || IDENTITY_RE.test(`${f.title} ${f.category} ${f.description ?? ""}`),
      );
      const f = formatFindings(idFindings, "IDENTITY & MANAGEMENT FINDINGS");
      const t = extractManagementPlane(input.topologyJson);
      if (!f && !t) return null;
      return [f, t].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "observability",
    number: 8,
    title: "Logging, Monitoring & Observability",
    charter: [
      "Flow log / Traffic Analytics / diagnostic-settings coverage — quantify it from the MEASURED coverage ratios (X of Y NSGs, gateways, firewalls)",
      "Detection posture: what malicious activity would currently be visible vs invisible given the actual coverage",
      "Alerting posture: what the metric/activity-log alert counts say about operational readiness",
      "Log centralization and retention: workspaces, retention windows",
      "Each relevant finding analyzed in depth with concrete Azure remediation steps",
    ],
    maxCompletionTokens: 4000,
    slice(input) {
      const f = formatFindings(byPattern(input.findings, MONITORING_RE), "OBSERVABILITY FINDINGS");
      const posture = extractObservabilityPosture(input.topologyJson);
      if (!f && !posture) return null;
      return [f, posture].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "resilience",
    number: 9,
    title: "Resilience & Availability",
    charter: [
      "Zone redundancy posture across gateways, firewalls, and load balancers",
      "Capacity headroom: read the MEASURED gateway/ExpressRoute/SNAT utilization — is there room to absorb a failover event, or is the estate already near its ceiling?",
      "Failure-mode analysis: what breaks in a zone or region outage",
      "Health probe coverage and failover behavior",
      "Each relevant finding analyzed in depth with concrete Azure remediation steps",
    ],
    maxCompletionTokens: 4000,
    slice(input) {
      const f = formatFindings(byPattern(input.findings, RESILIENCE_RE), "RESILIENCE FINDINGS");
      const t = extractResilience(input.topologyJson);
      const util = extractUtilizationTelemetry(input.topologyJson);
      if (!f && !t && !util) return null;
      return [f, t, util].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "finops",
    number: 10,
    title: "FinOps & Cost Optimization",
    charter: [
      "Network cost-waste findings: orphaned public IPs, idle gateways, oversized SKUs",
      "Anchor the analysis in the MEASURED month-to-date egress spend when present — actuals first, estimates second",
      "Estimated monthly savings, each figure marked [VERIFY] (static-price approximations)",
      "Cost-risk tradeoffs: where saving money would weaken the security posture — and where it wouldn't",
    ],
    maxCompletionTokens: 4000,
    slice(input) {
      const costFindings = input.findings.filter(
        (f) =>
          (typeof f.estCostImpact === "number" && f.estCostImpact > 0) ||
          COST_RE.test(`${f.title} ${f.category}`),
      );
      const f = formatFindings(costFindings, "COST FINDINGS");
      const egress = extractEgressCost(input.topologyJson);
      if (!f && !egress) return null;
      return [f, egress].filter(Boolean).join("\n\n");
    },
  },
  {
    id: "compliance",
    number: 11,
    title: "Compliance Framework Mapping",
    charter: [
      "Map findings to framework controls referenced in the data (NIST SP 800-53, CIS Azure, Well-Architected, Zero Trust)",
      "Reconcile with Microsoft Defender for Cloud's own unhealthy network assessments when present — where Microsoft's view and this assessment agree, say so; where this assessment sees more, say why",
      "Gap register table: control, requirement, current state, gap",
      "Audit-readiness narrative: what an assessor would flag first",
      "Only cite control IDs that appear in the finding data — do not invent mappings",
    ],
    maxCompletionTokens: 4000,
    slice(input) {
      const defender = extractDefenderPosture(input.topologyJson);
      if (!input.findings.length && !defender) return null;
      const lines = ["=== ALL FINDINGS (condensed for framework mapping) ==="];
      for (const f of input.findings) {
        const text = `${f.title} ${f.description ?? ""} ${f.recommendation ?? ""}`;
        const frameworks = text.match(new RegExp(FRAMEWORK_RE.source, "gi"));
        lines.push(`- [${f.severity}] ${f.title} (${f.category})${frameworks?.length ? ` — frameworks: ${[...new Set(frameworks)].join(", ")}` : ""}`);
      }
      return [lines.join("\n"), defender].filter(Boolean).join("\n\n").slice(0, MAX_SLICE_CHARS);
    },
  },
  {
    id: "remediation",
    number: 12,
    title: "Prioritized Remediation Roadmap",
    charter: [
      "Prioritize every finding by risk (severity, exploitability, blast radius) vs effort",
      "30/60/90-day phased roadmap with concrete tasks",
      "Dependencies between remediation tasks",
      "Validation step for each phase (how the client proves the fix landed)",
    ],
    maxCompletionTokens: 6000,
    slice(input) {
      if (!input.findings.length) return null;
      const lines = [`=== ALL FINDINGS FOR PRIORITIZATION (${input.findings.length}) ===`];
      for (const f of input.findings) {
        lines.push(`- [${f.severity}] ${f.title} (${f.category})`);
        if (f.recommendation) lines.push(`  Recommendation: ${f.recommendation}`);
        if (typeof f.estCostImpact === "number" && f.estCostImpact > 0) {
          lines.push(`  Est. monthly cost impact: $${f.estCostImpact} [VERIFY]`);
        }
      }
      return lines.join("\n").slice(0, MAX_SLICE_CHARS);
    },
  },
];

// ── Abbreviations glossary (Appendix D — deterministic) ───────────────────────

export const ABBREVIATIONS: Array<[string, string]> = [
  ["ACL", "Access control list"],
  ["AGW", "Application Gateway"],
  ["ARM", "Azure Resource Manager"],
  ["ASN", "Autonomous system number"],
  ["BGP", "Border Gateway Protocol"],
  ["CIS", "Center for Internet Security"],
  ["DDoS", "Distributed denial of service"],
  ["DNS", "Domain Name System"],
  ["ER", "ExpressRoute"],
  ["JIT", "Just-in-time (VM access)"],
  ["LB", "Load balancer"],
  ["NAT", "Network address translation"],
  ["NIST", "National Institute of Standards and Technology"],
  ["NSG", "Network security group"],
  ["NVA", "Network virtual appliance"],
  ["PE", "Private endpoint"],
  ["PIP", "Public IP address"],
  ["RBAC", "Role-based access control"],
  ["SKU", "Stock-keeping unit (service tier)"],
  ["SLA", "Service level agreement"],
  ["SPOF", "Single point of failure"],
  ["UDR", "User-defined route"],
  ["VNet", "Virtual network"],
  ["VPN", "Virtual private network"],
  ["WAF", "Web application firewall"],
];
