"""Static Azure networking price table — monthly USD estimates.

IMPORTANT: These are static list-price ESTIMATES (East US, pay-as-you-go,
730 hrs/month) used only to size cost-impact findings. They do not reflect
the client's negotiated rates, reservations, or region. Every figure
derived from this table MUST be rendered with a [VERIFY] flag in reports
and client-facing copy per CBTS review policy.
"""

from __future__ import annotations

HOURS_PER_MONTH = 730

# Public IP addresses (per IP, per month)
PUBLIC_IP_STANDARD_MONTHLY = 3.65  # $0.005/hr
PUBLIC_IP_BASIC_MONTHLY = 2.92  # $0.004/hr

# VPN Gateway SKUs (gateway hours only, per month)
VPN_GATEWAY_MONTHLY: dict[str, float] = {
    "Basic": 26.28,
    "VpnGw1": 138.70,
    "VpnGw2": 357.70,
    "VpnGw3": 912.50,
    "VpnGw4": 1533.00,
    "VpnGw5": 2664.50,
    "VpnGw1AZ": 264.99,
    "VpnGw2AZ": 445.30,
    "VpnGw3AZ": 1131.50,
    "VpnGw4AZ": 1898.00,
    "VpnGw5AZ": 3285.00,
}

# ExpressRoute gateway SKUs (gateway hours only, per month)
ER_GATEWAY_MONTHLY: dict[str, float] = {
    "Standard": 138.70,
    "HighPerformance": 357.70,
    "UltraPerformance": 1825.00,
    "ErGw1AZ": 138.70,
    "ErGw2AZ": 357.70,
    "ErGw3AZ": 1825.00,
}

# NAT Gateway (resource hours only; data processing excluded)
NAT_GATEWAY_MONTHLY = 32.85  # $0.045/hr

# Azure Firewall (deployment hours only; data processing excluded)
FIREWALL_MONTHLY: dict[str, float] = {
    "Basic": 288.35,  # $0.395/hr
    "Standard": 912.50,  # $1.25/hr
    "Premium": 1277.50,  # $1.75/hr
}

# Ordered ladders used for downsize suggestions (smallest → largest)
VPN_SKU_LADDER: list[str] = ["VpnGw1", "VpnGw2", "VpnGw3", "VpnGw4", "VpnGw5"]
VPN_SKU_LADDER_AZ: list[str] = ["VpnGw1AZ", "VpnGw2AZ", "VpnGw3AZ", "VpnGw4AZ", "VpnGw5AZ"]


def vpn_gateway_monthly(sku_name: str) -> float | None:
    """Monthly estimate for a VPN gateway SKU, or None if unknown."""
    return VPN_GATEWAY_MONTHLY.get(sku_name)


def er_gateway_monthly(sku_name: str) -> float | None:
    """Monthly estimate for an ExpressRoute gateway SKU, or None if unknown."""
    return ER_GATEWAY_MONTHLY.get(sku_name)


def gateway_monthly(gateway_type: str, sku_name: str) -> float | None:
    """Monthly estimate for a virtual network gateway by type and SKU."""
    if gateway_type == "ExpressRoute":
        return er_gateway_monthly(sku_name)
    return vpn_gateway_monthly(sku_name)


def next_smaller_vpn_sku(sku_name: str) -> str | None:
    """Return the next-smaller VPN SKU on the same (AZ / non-AZ) ladder."""
    for ladder in (VPN_SKU_LADDER, VPN_SKU_LADDER_AZ):
        if sku_name in ladder:
            idx = ladder.index(sku_name)
            return ladder[idx - 1] if idx > 0 else None
    return None
