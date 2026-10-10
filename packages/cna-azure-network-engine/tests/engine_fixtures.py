"""A fictional Resource Graph export covering every mapped type (subscription and names are samples).

This directory is deliberately not a package: pytest would otherwise name it ``tests`` and collide
with the monorepo's root ``tests`` package when both run in one session.
"""

from __future__ import annotations

SUB = "00000000-0000-0000-0000-000000000001"
RG = "hcw-sample-rg"
BASE = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network"


def rid(kind: str, name: str) -> str:
    return f"{BASE}/{kind}/{name}"


def row(segment: str, name: str, rtype: str, properties: dict, **extra) -> dict:
    base = {
        "id": rid(segment, name),
        "name": name,
        "type": rtype,
        "location": "eastus",
        "properties": properties,
    }
    base.update(extra)
    return base


VNET = rid("virtualNetworks", "hcw-sample-vnet")
NSG = rid("networkSecurityGroups", "hcw-sample-nsg")
RT = rid("routeTables", "hcw-sample-rt")
PIP = rid("publicIPAddresses", "hcw-sample-pip")
LB = rid("loadBalancers", "hcw-sample-lb")
GW = rid("virtualNetworkGateways", "hcw-sample-gw")
CONN = rid("connections", "hcw-sample-conn")
PE = rid("privateEndpoints", "hcw-sample-pe")
PDNS = rid("privateDnsZones", "privatelink.blob.core.windows.net")
NAT = rid("natGateways", "hcw-sample-nat")
BASTION = rid("bastionHosts", "hcw-sample-bastion")
FW = rid("azureFirewalls", "hcw-sample-fw")
FWPOL = rid("firewallPolicies", "hcw-sample-fwpol")
AGW = rid("applicationGateways", "hcw-sample-agw")
WAFPOL = rid("ApplicationGatewayWebApplicationFirewallPolicies", "hcw-sample-waf")
ER = rid("expressRouteCircuits", "hcw-sample-er")
VWAN = rid("virtualWans", "hcw-sample-vwan")
VHUB = rid("virtualHubs", "hcw-sample-hub")
RS = rid("virtualHubs", "hcw-sample-routeserver")
FLOWLOG = f"{BASE}/networkWatchers/NetworkWatcher_eastus/flowLogs/hcw-sample-flowlog"
FDWAF = rid("frontdoorWebApplicationFirewallPolicies", "hcwsamplefdwaf")


def export_rows() -> list[dict]:
    return [
        row(
            "virtualNetworks",
            "hcw-sample-vnet",
            "Microsoft.Network/virtualNetworks",
            {
                "addressSpace": {"addressPrefixes": ["10.0.0.0/16"]},
                "dhcpOptions": {"dnsServers": ["10.0.0.4"]},
                "enableDdosProtection": False,
                "subnets": [
                    {
                        "id": f"{VNET}/subnets/app",
                        "name": "app",
                        "properties": {
                            "addressPrefix": "10.0.1.0/24",
                            "networkSecurityGroup": {"id": NSG},
                            "routeTable": {"id": RT},
                            "ipConfigurations": [{"id": "/nic/1"}],
                            "delegations": [
                                {"properties": {"serviceName": "Microsoft.Web/serverFarms"}}
                            ],
                        },
                    },
                    {
                        "id": f"{VNET}/subnets/GatewaySubnet",
                        "name": "GatewaySubnet",
                        "properties": {"addressPrefix": "10.0.255.0/27"},
                    },
                ],
                "virtualNetworkPeerings": [
                    {
                        "id": f"{VNET}/virtualNetworkPeerings/to-spoke",
                        "name": "to-spoke",
                        "properties": {
                            "remoteVirtualNetwork": {
                                "id": f"{BASE}/virtualNetworks/hcw-sample-spoke"
                            },
                            "peeringState": "Connected",
                            "allowForwardedTraffic": True,
                            "allowGatewayTransit": True,
                            "useRemoteGateways": False,
                        },
                    }
                ],
            },
            tags={"env": "sample"},
        ),
        row(
            "networkSecurityGroups",
            "hcw-sample-nsg",
            "microsoft.network/networksecuritygroups",
            {
                "securityRules": [
                    {
                        "name": "allow-ssh",
                        "properties": {
                            "priority": 100,
                            "direction": "Inbound",
                            "access": "Allow",
                            "protocol": "Tcp",
                            "sourceAddressPrefix": "Internet",
                            "destinationAddressPrefix": "*",
                            "destinationPortRange": "22",
                        },
                    }
                ],
                "defaultSecurityRules": [
                    {
                        "name": "DenyAllInBound",
                        "properties": {
                            "priority": 65500,
                            "direction": "Inbound",
                            "access": "Deny",
                            "protocol": "*",
                        },
                    }
                ],
                "subnets": [{"id": f"{VNET}/subnets/app"}],
                "flowLogs": [{"id": FLOWLOG}],
            },
        ),
        row(
            "routeTables",
            "hcw-sample-rt",
            "microsoft.network/routetables",
            {
                "routes": [
                    {
                        "name": "default",
                        "properties": {"addressPrefix": "0.0.0.0/0", "nextHopType": "Internet"},
                    }
                ],
                "subnets": [{"id": f"{VNET}/subnets/app"}],
                "disableBgpRoutePropagation": True,
            },
        ),
        row(
            "publicIPAddresses",
            "hcw-sample-pip",
            "microsoft.network/publicipaddresses",
            {"publicIPAllocationMethod": "Static", "ipAddress": "203.0.113.10"},
            sku={"name": "Basic"},
            zones=[],
        ),
        row(
            "loadBalancers",
            "hcw-sample-lb",
            "microsoft.network/loadbalancers",
            {
                "frontendIPConfigurations": [
                    {"name": "fe", "properties": {"publicIPAddress": {"id": PIP}}, "zones": ["1"]}
                ],
                "loadBalancingRules": [
                    {
                        "name": "https",
                        "properties": {"protocol": "Tcp", "frontendPort": 443, "backendPort": 443},
                    }
                ],
                "probes": [{"name": "p", "properties": {"protocol": "Tcp", "port": 443}}],
            },
            sku={"name": "Standard"},
        ),
        row(
            "virtualNetworkGateways",
            "hcw-sample-gw",
            "microsoft.network/virtualnetworkgateways",
            {
                "gatewayType": "Vpn",
                "vpnType": "RouteBased",
                "sku": {"name": "Basic", "tier": "Basic"},
                "activeActive": False,
                "enableBgp": False,
                "vpnGatewayGeneration": "Generation1",
                "ipConfigurations": [
                    {
                        "properties": {
                            "subnet": {"id": f"{VNET}/subnets/GatewaySubnet"},
                            "publicIPAddress": {"id": PIP},
                        }
                    }
                ],
            },
        ),
        row(
            "connections",
            "hcw-sample-conn",
            "microsoft.network/connections",
            {
                "connectionType": "IPsec",
                "connectionStatus": "NotConnected",
                "virtualNetworkGateway1": {"id": GW},
                "sharedKey": "not-a-real-key",
            },
        ),
        row(
            "privateEndpoints",
            "hcw-sample-pe",
            "microsoft.network/privateendpoints",
            {
                "subnet": {"id": f"{VNET}/subnets/app"},
                "privateLinkServiceConnections": [
                    {
                        "name": "blob",
                        "properties": {
                            "privateLinkServiceId": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Storage/storageAccounts/hcwsample",
                            "groupIds": ["blob"],
                            "privateLinkServiceConnectionState": {"status": "Pending"},
                        },
                    }
                ],
            },
        ),
        {
            "id": f"{PE}/privateDnsZoneGroups/default",
            "name": "default",
            "type": "microsoft.network/privateendpoints/privatednszonegroups",
            "properties": {
                "privateDnsZoneConfigs": [{"name": "privatelink-blob-core-windows-net"}]
            },
        },
        row(
            "privateDnsZones",
            "privatelink.blob.core.windows.net",
            "microsoft.network/privatednszones",
            {"numberOfRecordSets": 3},
            location="global",
        ),
        {
            "id": f"{PDNS}/virtualNetworkLinks/link",
            "name": "link",
            "type": "microsoft.network/privatednszones/virtualnetworklinks",
            "location": "global",
            "properties": {"virtualNetwork": {"id": VNET}, "registrationEnabled": False},
        },
        row(
            "natGateways",
            "hcw-sample-nat",
            "microsoft.network/natgateways",
            {"publicIpAddresses": [{"id": PIP}]},
            sku={"name": "Standard"},
        ),
        row(
            "bastionHosts",
            "hcw-sample-bastion",
            "microsoft.network/bastionhosts",
            {
                "scaleUnits": 2,
                "enableTunneling": True,
                "ipConfigurations": [
                    {"properties": {"subnet": {"id": f"{VNET}/subnets/AzureBastionSubnet"}}}
                ],
            },
            sku={"name": "Standard"},
        ),
        row(
            "azureFirewalls",
            "hcw-sample-fw",
            "microsoft.network/azurefirewalls",
            {
                "sku": {"tier": "Standard"},
                "threatIntelMode": "Alert",
                "firewallPolicy": {"id": FWPOL},
                "ipConfigurations": [
                    {
                        "properties": {
                            "subnet": {"id": f"{VNET}/subnets/AzureFirewallSubnet"},
                            "publicIPAddress": {"id": PIP},
                        }
                    }
                ],
            },
            zones=["1", "2", "3"],
        ),
        row(
            "firewallPolicies",
            "hcw-sample-fwpol",
            "microsoft.network/firewallpolicies",
            {
                "threatIntelMode": "Deny",
                "sku": {"tier": "Standard"},
                "dnsSettings": {"enableProxy": True},
            },
        ),
        row(
            "applicationGateways",
            "hcw-sample-agw",
            "microsoft.network/applicationgateways",
            {
                "sku": {"name": "WAF_v2", "tier": "WAF_v2", "capacity": 2},
                "gatewayIPConfigurations": [
                    {"properties": {"subnet": {"id": f"{VNET}/subnets/agw"}}}
                ],
                "webApplicationFirewallConfiguration": {
                    "enabled": True,
                    "firewallMode": "Detection",
                    "ruleSetType": "OWASP",
                    "ruleSetVersion": "3.2",
                },
                "firewallPolicy": {"id": WAFPOL},
            },
            zones=["1"],
        ),
        row(
            "ApplicationGatewayWebApplicationFirewallPolicies",
            "hcw-sample-waf",
            "microsoft.network/applicationgatewaywebapplicationfirewallpolicies",
            {"policySettings": {"state": "Enabled", "mode": "Detection"}},
        ),
        row(
            "expressRouteCircuits",
            "hcw-sample-er",
            "microsoft.network/expressroutecircuits",
            {
                "serviceProviderProperties": {
                    "serviceProviderName": "Sample Provider",
                    "peeringLocation": "Sample City",
                    "bandwidthInMbps": 1000,
                },
                "circuitProvisioningState": "Enabled",
                "peerings": [{"properties": {"peeringType": "AzurePrivatePeering"}}],
            },
            sku={"tier": "Standard", "family": "MeteredData"},
        ),
        row(
            "virtualWans",
            "hcw-sample-vwan",
            "microsoft.network/virtualwans",
            {"type": "Standard", "allowVnetToVnetTraffic": True},
        ),
        row(
            "virtualHubs",
            "hcw-sample-hub",
            "microsoft.network/virtualhubs",
            {
                "addressPrefix": "10.9.0.0/24",
                "virtualWan": {"id": VWAN},
                "routingState": "Provisioned",
                "virtualRouterAsn": 65515,
            },
        ),
        row(
            "virtualHubs",
            "hcw-sample-routeserver",
            "microsoft.network/virtualhubs",
            {
                "virtualRouterAsn": 65515,
                "virtualRouterIps": ["10.0.254.4"],
                "allowBranchToBranchTraffic": True,
            },
            kind="RouteServer",
        ),
        {
            "id": FLOWLOG,
            "name": "hcw-sample-flowlog",
            "type": "microsoft.network/networkwatchers/flowlogs",
            "location": "eastus",
            "properties": {
                "targetResourceId": NSG,
                "enabled": True,
                "retentionPolicy": {"days": 30},
                "flowAnalyticsConfiguration": {
                    "networkWatcherFlowAnalyticsConfiguration": {"enabled": False}
                },
            },
        },
        row(
            "frontdoorWebApplicationFirewallPolicies",
            "hcwsamplefdwaf",
            "microsoft.network/frontdoorwebapplicationfirewallpolicies",
            {
                "policySettings": {"mode": "Detection", "enabledState": "Enabled"},
                "customRules": {"rules": [{}]},
                "managedRules": {"managedRuleSets": [{}, {}]},
            },
            location="global",
        ),
        {
            "id": rid("networkInterfaces", "hcw-sample-nic"),
            "name": "hcw-sample-nic",
            "type": "microsoft.network/networkinterfaces",
            "location": "eastus",
            "properties": {},
        },
        {
            "id": rid("localNetworkGateways", "hcw-sample-lng"),
            "name": "hcw-sample-lng",
            "type": "microsoft.network/localnetworkgateways",
            "location": "eastus",
            "properties": {},
        },
        {
            "id": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Compute/virtualMachines/hcw-sample-vm",
            "name": "hcw-sample-vm",
            "type": "microsoft.compute/virtualmachines",
            "location": "eastus",
            "properties": {},
        },
    ]
