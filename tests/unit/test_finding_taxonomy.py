"""Unit tests for finding taxonomy traffic-direction classification."""

from cna.core.finding_taxonomy import classify_traffic_direction


def test_rule_id_east_west():
    assert classify_traffic_direction("AZ-NET-005") == "east_west"
    assert classify_traffic_direction("AZ-NET-012") == "east_west"
    assert classify_traffic_direction("AZ-NET-002") == "east_west"
    assert classify_traffic_direction("AWS-NET-006") == "east_west"


def test_rule_id_north_south():
    assert classify_traffic_direction("AZ-NET-003") == "north_south"
    assert classify_traffic_direction("AZ-NET-007") == "north_south"
    assert classify_traffic_direction("AZ-NET-017") == "north_south"
    assert classify_traffic_direction("AWS-NET-003") == "north_south"
    assert classify_traffic_direction("AZ-COST-001") == "north_south"
    assert classify_traffic_direction("AZ-BCDR-002") == "north_south"


def test_rule_id_management():
    assert classify_traffic_direction("AZ-NET-006") == "management"
    assert classify_traffic_direction("AZ-NET-014") == "management"
    assert classify_traffic_direction("AZ-NET-015") == "management"
    assert classify_traffic_direction("AWS-NET-002") == "management"


def test_unknown_cost_bcdr_prefix_defaults_north_south():
    assert classify_traffic_direction("AZ-COST-099") == "north_south"
    assert classify_traffic_direction("AZ-BCDR-099") == "north_south"


def test_category_fallback():
    assert classify_traffic_direction("", category="Network Segmentation") == "east_west"
    assert classify_traffic_direction("", category="Routing & Transit") == "east_west"
    assert classify_traffic_direction("", category="Remote Access") == "north_south"
    assert classify_traffic_direction("", category="Observability") == "management"
    assert classify_traffic_direction("", category="Monitoring & Visibility") == "management"


def test_resource_type_fallback():
    assert (
        classify_traffic_direction("", resource_type="Microsoft.Network/publicIPAddresses")
        == "north_south"
    )
    assert (
        classify_traffic_direction(
            "", resource_type="Microsoft.Network/virtualNetworks/virtualNetworkPeerings"
        )
        == "east_west"
    )
    assert (
        classify_traffic_direction("", resource_type="Microsoft.Network/bastionHosts")
        == "management"
    )


def test_unclassifiable_returns_empty():
    assert classify_traffic_direction("") == ""
    assert classify_traffic_direction("XX-FOO-001", "Unknown Cat", "Some/Type") == ""
