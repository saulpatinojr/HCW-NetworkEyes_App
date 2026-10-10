// Static Azure networking price table — monthly USD estimates.
//
// IMPORTANT: These are static list-price ESTIMATES (East US, pay-as-you-go,
// 730 hrs/month) mirroring cna/modules/network/analysis/azure_network_prices.py
// (keep the two in sync). They do not reflect the client's negotiated rates,
// reservations, or region. Every figure derived from this table MUST be
// rendered with a [VERIFY] flag in reports and client-facing copy per CBTS
// review policy.

export const HOURS_PER_MONTH = 730;

// Public IP addresses (per IP, per month)
export const PUBLIC_IP_STANDARD_MONTHLY = 3.65; // $0.005/hr
export const PUBLIC_IP_BASIC_MONTHLY = 2.92; // $0.004/hr

// VPN Gateway SKUs (gateway hours only, per month)
export const VPN_GATEWAY_MONTHLY: Record<string, number> = {
  Basic: 26.28,
  VpnGw1: 138.7,
  VpnGw2: 357.7,
  VpnGw3: 912.5,
  VpnGw4: 1533.0,
  VpnGw5: 2664.5,
  VpnGw1AZ: 264.99,
  VpnGw2AZ: 445.3,
  VpnGw3AZ: 1131.5,
  VpnGw4AZ: 1898.0,
  VpnGw5AZ: 3285.0,
};

// ExpressRoute gateway SKUs (gateway hours only, per month)
export const ER_GATEWAY_MONTHLY: Record<string, number> = {
  Standard: 138.7,
  HighPerformance: 357.7,
  UltraPerformance: 1825.0,
  ErGw1AZ: 138.7,
  ErGw2AZ: 357.7,
  ErGw3AZ: 1825.0,
};

// NAT Gateway (resource hours only; data processing excluded)
export const NAT_GATEWAY_MONTHLY = 32.85; // $0.045/hr

// Azure Firewall (deployment hours only; data processing excluded)
export const FIREWALL_MONTHLY: Record<string, number> = {
  Basic: 288.35, // $0.395/hr
  Standard: 912.5, // $1.25/hr
  Premium: 1277.5, // $1.75/hr
};

// Azure Bastion (base deployment; Standard/Premium include 2 scale units)
export const BASTION_MONTHLY: Record<string, number> = {
  Developer: 0,
  Basic: 138.7, // $0.19/hr
  Standard: 211.7, // $0.29/hr
  Premium: 306.6, // $0.42/hr
};
export const BASTION_EXTRA_SCALE_UNIT_MONTHLY = 102.2; // $0.14/hr per unit above 2

// Application Gateway v2 (fixed deployment hours + capacity units)
export const APPGW_V2_FIXED_MONTHLY: Record<string, number> = {
  Standard_v2: 179.58, // $0.246/hr
  WAF_v2: 323.39, // $0.443/hr
};
export const APPGW_V2_CU_MONTHLY: Record<string, number> = {
  Standard_v2: 5.84, // $0.008/CU-hr
  WAF_v2: 10.51, // $0.0144/CU-hr
};
// Application Gateway v1 (instance hours, Medium/Large; Small dev-only)
export const APPGW_V1_MONTHLY: Record<string, number> = {
  Standard_Small: 18.25,
  Standard_Medium: 51.1,
  Standard_Large: 233.6,
  WAF_Medium: 91.98,
  WAF_Large: 327.04,
};

// Private Link (endpoint hours only; per-GB data processing excluded)
export const PRIVATE_ENDPOINT_MONTHLY = 7.3; // $0.01/hr per endpoint

// Private DNS zone (first 25 zones; per-query charges excluded)
export const PRIVATE_DNS_ZONE_MONTHLY = 0.5;

export function gatewayMonthly(gatewayType: string, skuName: string): number | null {
  const table = gatewayType === "ExpressRoute" ? ER_GATEWAY_MONTHLY : VPN_GATEWAY_MONTHLY;
  return table[skuName] ?? null;
}

export function bastionMonthly(skuName: string, scaleUnits: number): number | null {
  const base = BASTION_MONTHLY[skuName];
  if (base === undefined) return null;
  const extraUnits = skuName === "Standard" || skuName === "Premium" ? Math.max(0, scaleUnits - 2) : 0;
  return base + extraUnits * BASTION_EXTRA_SCALE_UNIT_MONTHLY;
}

export function appGatewayMonthly(skuName: string, capacityUnits: number | null): number | null {
  const v2Fixed = APPGW_V2_FIXED_MONTHLY[skuName];
  if (v2Fixed !== undefined) {
    return v2Fixed + (capacityUnits ?? 0) * (APPGW_V2_CU_MONTHLY[skuName] ?? 0);
  }
  const v1 = APPGW_V1_MONTHLY[skuName];
  if (v1 !== undefined) return v1 * Math.max(1, capacityUnits ?? 1);
  return null;
}

export function publicIpMonthly(skuName: string): number {
  return skuName === "Basic" ? PUBLIC_IP_BASIC_MONTHLY : PUBLIC_IP_STANDARD_MONTHLY;
}

export function formatUsd(value: number): string {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
