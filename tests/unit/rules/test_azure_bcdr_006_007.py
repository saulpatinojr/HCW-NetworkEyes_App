"""One fixture per rule for ``AZ-BCDR-006`` (App Gateway zones) and ``AZ-BCDR-007`` (LB zones)."""

from __future__ import annotations

from cna.core.findings_schema import FindingSeverity
from cna.core.topology.azure import (
    ApplicationGateway,
    AzureLoadBalancer,
    AzureSubscriptionTopology,
    AzureTopology,
)
from cna_azure_network_engine.rules import RULES, evaluate

SUB = "00000000-0000-0000-0000-000000000001"
RG = "hcw-sample-rg"
LOC = "westeurope"


def _findings(sub: AzureSubscriptionTopology, rule_id: str):
    topology = AzureTopology(
        engagement_id="hcw-sample-engagement", tenant_id="t", subscriptions=[sub]
    )
    return [f for f in evaluate(topology).findings if f.rule_id == rule_id]


def _sub(**overrides) -> AzureSubscriptionTopology:
    base = {"subscription_id": SUB, "tenant_id": "t"}
    base.update(overrides)
    return AzureSubscriptionTopology(**base)


def _appgw(sku: str, zones: list[str]) -> ApplicationGateway:
    return ApplicationGateway(
        id=f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/applicationGateways/hcw-sample-agw",
        name="hcw-sample-agw",
        location=LOC,
        resource_group=RG,
        sku_name=sku,
        subnet_id="/subnet",
        waf_enabled=True,
        waf_mode="Prevention",
        zones=zones,
    )


def _lb(sku: str, zones: list[str]) -> AzureLoadBalancer:
    return AzureLoadBalancer(
        id=f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/loadBalancers/hcw-sample-lb",
        name="hcw-sample-lb",
        location=LOC,
        resource_group=RG,
        sku_name=sku,
        zones=zones,
    )


class TestAzBcdr006AppGatewayNotZoneRedundant:
    RULE = "AZ-BCDR-006"

    def test_v2_gateway_in_one_zone_is_medium(self):
        found = _findings(_sub(application_gateways=[_appgw("Standard_v2", ["1"])]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.MEDIUM
        assert found[0].category == "BC/DR"

    def test_v2_gateway_with_no_zones_fires(self):
        assert len(_findings(_sub(application_gateways=[_appgw("WAF_v2", [])]), self.RULE)) == 1

    def test_zone_redundant_v2_gateway_does_not_fire(self):
        assert (
            _findings(_sub(application_gateways=[_appgw("WAF_v2", ["1", "2", "3"])]), self.RULE)
            == []
        )

    def test_v1_sku_cannot_be_zonal_and_does_not_fire(self):
        assert (
            _findings(_sub(application_gateways=[_appgw("Standard_Medium", [])]), self.RULE) == []
        )


class TestAzBcdr007LoadBalancerNotZoneRedundant:
    RULE = "AZ-BCDR-007"

    def test_standard_lb_in_one_zone_is_low(self):
        found = _findings(_sub(load_balancers=[_lb("Standard", ["2"])]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.LOW

    def test_standard_lb_with_zones_does_not_fire(self):
        assert _findings(_sub(load_balancers=[_lb("Standard", ["1", "2", "3"])]), self.RULE) == []

    def test_basic_lb_is_az_net_026_not_this_rule(self):
        sub = _sub(load_balancers=[_lb("Basic", [])])
        assert _findings(sub, self.RULE) == []
        assert len(_findings(sub, "AZ-NET-026")) == 1


class TestZoneRulesMatchThePlan:
    def test_numbering_and_severity(self):
        assert RULES["AZ-BCDR-006"][0].severity == FindingSeverity.MEDIUM
        assert RULES["AZ-BCDR-007"][0].severity == FindingSeverity.LOW
        assert all(RULES[r][0].applies_to == "export" for r in ("AZ-BCDR-006", "AZ-BCDR-007"))
