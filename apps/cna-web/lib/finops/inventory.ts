// Chargeable network inventory builder for the FinOps page.
//
// Reads the merged discovery topology (DiscoveryJob.topologyJson) and produces
// one row per network resource that bills monthly, with a static list-price
// estimate ([VERIFY]) and waste flags aligned with Microsoft's FinOps
// networking best practices (unattached public IPs, idle gateways, orphaned
// NAT gateways, unlinked private DNS zones, unprovisioned ER circuits).
// Field shapes mirror cna/core/topology_schema.py.

import {
  appGatewayMonthly,
  bastionMonthly,
  FIREWALL_MONTHLY,
  formatUsd,
  gatewayMonthly,
  NAT_GATEWAY_MONTHLY,
  PRIVATE_DNS_ZONE_MONTHLY,
  PRIVATE_ENDPOINT_MONTHLY,
  publicIpMonthly,
} from "./prices";

// ── Topology slices (subset of cna/core/topology_schema.py v1.3.0) ──────────

interface PublicIP {
  name: string;
  location: string;
  sku_name: string;
  allocation_method: string;
  ip_address: string | null;
  associated_resource_type: string | null;
}

interface VNetGateway {
  name: string;
  location: string;
  gateway_type: string; // "Vpn" | "ExpressRoute"
  sku_name: string;
  connections: { name: string; connection_status: string }[];
}

interface Firewall {
  name: string;
  location: string;
  sku_tier: string;
}

interface AppGateway {
  name: string;
  location: string;
  sku_name: string;
  sku_capacity: number | null;
  autoscale_min: number | null;
  autoscale_max: number | null;
}

interface NatGateway {
  name: string;
  location: string;
  associated_subnet_ids: string[];
}

interface BastionHost {
  name: string;
  location: string;
  sku_name: string;
  scale_units: number;
}

interface PrivateEndpoint {
  name: string;
  location: string;
  service_connections: { group_ids: string[] }[];
}

interface PrivateDnsZone {
  name: string;
  linked_vnet_ids: string[];
  record_count: number;
}

interface ExpressRouteCircuit {
  name: string;
  location: string;
  sku_tier: string;
  sku_family: string;
  bandwidth_mbps: number | null;
  circuit_provisioning_state: string;
}

export interface FinOpsSubscription {
  subscription_id: string;
  subscription_name: string | null;
  public_ips?: PublicIP[];
  virtual_network_gateways?: VNetGateway[];
  firewalls?: Firewall[];
  application_gateways?: AppGateway[];
  nat_gateways?: NatGateway[];
  bastion_hosts?: BastionHost[];
  private_endpoints?: PrivateEndpoint[];
  private_dns_zones?: PrivateDnsZone[];
  express_route_circuits?: ExpressRouteCircuit[];
  network_metrics?: { egress_cost_usd_mtd?: number | null } | null;
}

// ── Output shapes ────────────────────────────────────────────────────────────

export interface ChargeableRow {
  kind: string; // display group, e.g. "Public IP"
  name: string;
  subscriptionId: string;
  subscriptionName: string | null;
  region: string;
  sku: string;
  /** Static list-price estimate (USD/month), or null when not estimable. */
  estMonthlyUsd: number | null;
  /** Waste / attention flags, e.g. "unattached", "no connections". */
  flags: string[];
}

export interface ChargeableGroup {
  kind: string;
  rows: ChargeableRow[];
  estMonthlyUsd: number;
  flaggedCount: number;
}

export interface EgressSpendRow {
  subscriptionId: string;
  subscriptionName: string | null;
  egressUsdMtd: number | null;
}

// ── Builders ─────────────────────────────────────────────────────────────────

export function buildEgressSpend(subs: FinOpsSubscription[]): EgressSpendRow[] {
  return subs
    .map((s) => ({
      subscriptionId: s.subscription_id,
      subscriptionName: s.subscription_name,
      egressUsdMtd: s.network_metrics?.egress_cost_usd_mtd ?? null,
    }))
    .sort((a, b) => (b.egressUsdMtd ?? -1) - (a.egressUsdMtd ?? -1));
}

export function buildChargeableInventory(subs: FinOpsSubscription[]): ChargeableGroup[] {
  const rows: ChargeableRow[] = [];

  for (const sub of subs) {
    const base = {
      subscriptionId: sub.subscription_id,
      subscriptionName: sub.subscription_name,
    };

    for (const ip of sub.public_ips ?? []) {
      const unattached = !ip.associated_resource_type;
      rows.push({
        ...base,
        kind: "Public IP",
        name: ip.name,
        region: ip.location,
        sku: `${ip.sku_name} / ${ip.allocation_method}`,
        estMonthlyUsd: publicIpMonthly(ip.sku_name),
        flags: unattached ? ["unattached"] : [],
      });
    }

    for (const gw of sub.virtual_network_gateways ?? []) {
      const idle = (gw.connections ?? []).length === 0;
      rows.push({
        ...base,
        kind: gw.gateway_type === "ExpressRoute" ? "ExpressRoute Gateway" : "VPN Gateway",
        name: gw.name,
        region: gw.location,
        sku: gw.sku_name,
        estMonthlyUsd: gatewayMonthly(gw.gateway_type, gw.sku_name),
        flags: idle ? ["no connections"] : [],
      });
    }

    for (const fw of sub.firewalls ?? []) {
      rows.push({
        ...base,
        kind: "Azure Firewall",
        name: fw.name,
        region: fw.location,
        sku: fw.sku_tier,
        estMonthlyUsd: FIREWALL_MONTHLY[fw.sku_tier] ?? null,
        flags: [],
      });
    }

    for (const agw of sub.application_gateways ?? []) {
      const capacity = agw.sku_capacity ?? agw.autoscale_min ?? null;
      const capLabel =
        agw.autoscale_min != null
          ? `autoscale ${agw.autoscale_min}–${agw.autoscale_max ?? "?"} CU`
          : agw.sku_capacity != null
            ? `${agw.sku_capacity} CU`
            : "";
      rows.push({
        ...base,
        kind: "Application Gateway",
        name: agw.name,
        region: agw.location,
        sku: capLabel ? `${agw.sku_name} (${capLabel})` : agw.sku_name,
        estMonthlyUsd: appGatewayMonthly(agw.sku_name, capacity),
        flags: [],
      });
    }

    for (const nat of sub.nat_gateways ?? []) {
      const orphaned = (nat.associated_subnet_ids ?? []).length === 0;
      rows.push({
        ...base,
        kind: "NAT Gateway",
        name: nat.name,
        region: nat.location,
        sku: "Standard",
        estMonthlyUsd: NAT_GATEWAY_MONTHLY,
        flags: orphaned ? ["no subnets"] : [],
      });
    }

    for (const bastion of sub.bastion_hosts ?? []) {
      rows.push({
        ...base,
        kind: "Bastion",
        name: bastion.name,
        region: bastion.location,
        sku:
          bastion.scale_units > 2
            ? `${bastion.sku_name} (${bastion.scale_units} scale units)`
            : bastion.sku_name,
        estMonthlyUsd: bastionMonthly(bastion.sku_name, bastion.scale_units),
        flags: [],
      });
    }

    for (const pe of sub.private_endpoints ?? []) {
      const groupIds = (pe.service_connections ?? []).flatMap((c) => c.group_ids ?? []);
      rows.push({
        ...base,
        kind: "Private Endpoint",
        name: pe.name,
        region: pe.location,
        sku: groupIds.length ? groupIds.join(", ") : "—",
        estMonthlyUsd: PRIVATE_ENDPOINT_MONTHLY,
        flags: [],
      });
    }

    for (const zone of sub.private_dns_zones ?? []) {
      const unlinked = (zone.linked_vnet_ids ?? []).length === 0;
      rows.push({
        ...base,
        kind: "Private DNS Zone",
        name: zone.name,
        region: "global",
        sku: `${zone.record_count} records`,
        estMonthlyUsd: PRIVATE_DNS_ZONE_MONTHLY,
        flags: unlinked ? ["no VNet links"] : [],
      });
    }

    for (const er of sub.express_route_circuits ?? []) {
      const notProvisioned = /notprovisioned/i.test(er.circuit_provisioning_state ?? "");
      rows.push({
        ...base,
        kind: "ExpressRoute Circuit",
        name: er.name,
        region: er.location,
        sku: `${er.sku_tier} ${er.sku_family}${er.bandwidth_mbps ? ` ${er.bandwidth_mbps} Mbps` : ""}`,
        // Circuit port fees vary by provider, bandwidth, and peering location.
        estMonthlyUsd: null,
        flags: notProvisioned ? ["not provisioned"] : [],
      });
    }
  }

  // Group by kind; flagged rows first within each group, then by est cost desc.
  const byKind = new Map<string, ChargeableRow[]>();
  for (const row of rows) {
    const list = byKind.get(row.kind) ?? [];
    list.push(row);
    byKind.set(row.kind, list);
  }

  const groups: ChargeableGroup[] = [...byKind.entries()].map(([kind, groupRows]) => {
    groupRows.sort(
      (a, b) =>
        (b.flags.length ? 1 : 0) - (a.flags.length ? 1 : 0) ||
        (b.estMonthlyUsd ?? 0) - (a.estMonthlyUsd ?? 0),
    );
    return {
      kind,
      rows: groupRows,
      estMonthlyUsd: groupRows.reduce((s, r) => s + (r.estMonthlyUsd ?? 0), 0),
      flaggedCount: groupRows.filter((r) => r.flags.length > 0).length,
    };
  });

  // Categories with no resources never appear (no $0 rows); order by est cost.
  return groups.sort((a, b) => b.estMonthlyUsd - a.estMonthlyUsd);
}

export { formatUsd };
