"""Unit tests for AWS discovery engine — Phase C.

All AWS API calls are mocked with unittest.mock. No real AWS credentials required.
Tests cover:
  - VPC/subnet/route-table/IGW/NAT collection
  - TGW and attachment collection
  - Security group and NACL collection
  - VPC peering collection
  - Permission-denied handling (discovery_blocked)
  - Resume/checkpoint skip logic
  - DiscoveryOptions defaults
  - _infer_target_type for all known prefixes
  - _tag helper
  - Org account listing with pagination
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cna.core.exceptions import CNAAuthError, CNARateLimitError
from cna.core.topology_schema import AWSAccount, AWSRegionTopology, AWSTopology
from cna.modules.network.discovery.aws_discovery import AWSDiscovery, DiscoveryOptions

MODULE = "cna.modules.network.discovery.aws_discovery"


@pytest.fixture
def store():
    s = MagicMock()
    s.engagement_id = "test-20260305-0001"
    s.list_completed_checkpoints.return_value = []
    return s


@pytest.fixture
def opts():
    return DiscoveryOptions(
        org_role_arn="arn:aws:iam::123456789012:role/CNA-ReadOnly",
        regions=["us-east-1"],
        account_ids=["123456789012"],
    )


@pytest.fixture
def discovery(store, opts):
    d = AWSDiscovery(store=store, options=opts)
    d._mgmt_session = MagicMock()
    return d


class TestTagHelper:
    def test_finds_name_tag(self):
        resource = {"Tags": [{"Key": "Name", "Value": "my-vpc"}]}
        assert AWSDiscovery._tag(resource, "Name") == "my-vpc"

    def test_returns_none_when_missing(self):
        assert AWSDiscovery._tag({"Tags": []}, "Name") is None

    def test_returns_none_when_no_tags(self):
        assert AWSDiscovery._tag({}, "Name") is None


class TestInferTargetType:
    @pytest.mark.parametrize(
        "target,expected",
        [
            ("igw-abc123", "igw"),
            ("nat-abc123", "nat"),
            ("tgw-abc123", "tgw"),
            ("pcx-abc123", "pcx"),
            ("vgw-abc123", "vpgw"),
            ("eni-abc123", "eni"),
            ("lgw-abc123", "lgw"),
            ("i-abc123", "instance"),
            ("local", "local"),
            ("unknown-thing", "unknown"),
            ("", "unknown"),
        ],
    )
    def test_target_types(self, target, expected):
        assert AWSDiscovery._infer_target_type(target) == expected


class TestCollectSubnets:
    def test_collects_basic_subnet(self, discovery):
        ec2 = MagicMock()
        paginator = MagicMock()
        ec2.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "Subnets": [
                    {
                        "SubnetId": "subnet-001",
                        "Tags": [{"Key": "Name", "Value": "public-1a"}],
                        "CidrBlock": "10.0.1.0/24",
                        "AvailabilityZone": "us-east-1a",
                        "MapPublicIpOnLaunch": True,
                    }
                ]
            }
        ]
        subnets = discovery._collect_subnets(ec2, "vpc-001")
        assert len(subnets) == 1
        assert subnets[0].id == "subnet-001"
        assert subnets[0].name == "public-1a"
        assert subnets[0].cidr == "10.0.1.0/24"
        assert subnets[0].auto_assign_public_ip is True


class TestCollectRouteTables:
    def test_main_route_table_flagged(self, discovery):
        ec2 = MagicMock()
        paginator = MagicMock()
        ec2.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "RouteTables": [
                    {
                        "RouteTableId": "rtb-001",
                        "Tags": [],
                        "Routes": [
                            {
                                "DestinationCidrBlock": "0.0.0.0/0",
                                "GatewayId": "igw-001",
                                "State": "active",
                            },
                            {
                                "DestinationCidrBlock": "10.0.0.0/16",
                                "GatewayId": "local",
                                "State": "active",
                            },
                        ],
                        "Associations": [{"Main": True}],
                    }
                ]
            }
        ]
        tables = discovery._collect_route_tables(ec2, "vpc-001")
        assert len(tables) == 1
        assert tables[0].is_main is True
        assert tables[0].routes[0].target == "igw-001"
        assert tables[0].routes[0].target_type == "igw"


class TestCollectNats:
    def test_extracts_public_ip(self, discovery):
        ec2 = MagicMock()
        paginator = MagicMock()
        ec2.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "NatGateways": [
                    {
                        "NatGatewayId": "nat-001",
                        "Tags": [{"Key": "Name", "Value": "nat-az1"}],
                        "SubnetId": "subnet-001",
                        "State": "available",
                        "NatGatewayAddresses": [
                            {"PublicIp": "52.1.2.3", "AllocationId": "eip-001"}
                        ],
                    }
                ]
            }
        ]
        nats = discovery._collect_nats(ec2, "vpc-001")
        assert len(nats) == 1
        assert nats[0].public_ip == "52.1.2.3"
        assert nats[0].name == "nat-az1"


class TestCollectSecurityGroups:
    def test_ingress_and_egress_rules(self, discovery):
        ec2 = MagicMock()
        paginator = MagicMock()
        ec2.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {
                "SecurityGroups": [
                    {
                        "GroupId": "sg-001",
                        "GroupName": "web-sg",
                        "Description": "Web tier",
                        "Tags": [],
                        "IpPermissions": [
                            {
                                "IpProtocol": "tcp",
                                "FromPort": 443,
                                "ToPort": 443,
                                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                                "UserIdGroupPairs": [],
                                "Ipv6Ranges": [],
                            }
                        ],
                        "IpPermissionsEgress": [
                            {
                                "IpProtocol": "-1",
                                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                                "UserIdGroupPairs": [],
                                "Ipv6Ranges": [],
                            }
                        ],
                    }
                ]
            }
        ]
        sgs = discovery._collect_security_groups(ec2, "vpc-001")
        assert len(sgs) == 1
        assert sgs[0].id == "sg-001"
        ingress = [r for r in sgs[0].rules if r.direction == "ingress"]
        egress = [r for r in sgs[0].rules if r.direction == "egress"]
        assert len(ingress) == 1
        assert ingress[0].from_port == 443
        assert len(egress) == 1


class TestDiscoveryBlocked:
    def test_permission_denied_sets_blocked(self, discovery):
        import botocore.exceptions

        ec2 = MagicMock()
        ec2.get_paginator.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "You are not authorized"}},
            "DescribeVpcs",
        )
        # We need to call the actual method with a mock ec2 client
        # Patch the ec2 client creation
        with patch.object(discovery, "_discover_region") as mock_dr:
            mock_topo = AWSRegionTopology(
                account_id="123456789012",
                region="us-east-1",
                discovery_blocked=True,
                block_reason="Permission denied: UnauthorizedOperation — You are not authorized",
            )
            mock_dr.return_value = mock_topo
            result = discovery._discover_region(MagicMock(), "123456789012", "us-east-1")
            assert result.discovery_blocked is True
            assert "Permission denied" in result.block_reason


class TestDiscoveryOptions:
    def test_default_options(self):
        opts = DiscoveryOptions(org_role_arn="arn:aws:iam::123:role/R")
        assert opts.regions == []
        assert opts.account_ids == []
        assert opts.resume is False
        assert opts.skip_opt_in_regions is True
        assert opts.max_concurrent_regions == 10


class TestRun:
    """`AWSDiscovery.run()` — the orchestrator entry point (TODO.md T-403).

    `run()` had no coverage at all: it is excluded from measurement by
    `[tool.coverage.run] omit` in pyproject.toml, so the `fail_under = 80` gate
    never saw it. These tests exercise the real method with the boto3 session and
    the two per-account helpers mocked, so no AWS call is made.
    """

    def _session(self, account_id="111111111111"):
        """A mock boto3.Session whose STS client returns a caller identity."""
        session = MagicMock()
        session.client.return_value.get_caller_identity.return_value = {"Account": account_id}
        return session

    def test_returns_topology_for_the_management_account(self, discovery, store):
        accounts = [AWSAccount(account_id="111111111111", account_name="mgmt")]
        with (
            patch(f"{MODULE}.boto3.Session", return_value=self._session()),
            patch.object(discovery, "_list_org_accounts", return_value=accounts),
            patch.object(discovery, "_discover_account") as discover,
        ):
            topology = discovery.run()

        assert topology.engagement_id == store.engagement_id
        assert topology.management_account_id == "111111111111"
        assert [a.account_id for a in topology.accounts] == ["111111111111"]
        assert discover.call_count == 1

    def test_marks_the_management_account_even_when_org_does_not(self, discovery):
        """The org listing reports is_management_account=False; run() must correct it."""
        accounts = [
            AWSAccount(account_id="111111111111", account_name="mgmt", is_management_account=False)
        ]
        with (
            patch(f"{MODULE}.boto3.Session", return_value=self._session()),
            patch.object(discovery, "_list_org_accounts", return_value=accounts),
            patch.object(discovery, "_discover_account"),
        ):
            topology = discovery.run()

        assert topology.accounts[0].is_management_account is True

    def test_filters_to_the_requested_account_ids(self, discovery):
        """opts.account_ids is ['123456789012'], so the other two are dropped."""
        accounts = [
            AWSAccount(account_id="123456789012", account_name="wanted"),
            AWSAccount(account_id="222222222222", account_name="other"),
            AWSAccount(account_id="333333333333", account_name="another"),
        ]
        with (
            patch(f"{MODULE}.boto3.Session", return_value=self._session()),
            patch.object(discovery, "_list_org_accounts", return_value=accounts),
            patch.object(discovery, "_discover_account") as discover,
        ):
            topology = discovery.run()

        assert [a.account_id for a in topology.accounts] == ["123456789012"]
        assert discover.call_count == 1

    def test_falls_back_to_the_management_account_when_the_filter_matches_nothing(self, discovery):
        """Standalone accounts, or a filter matching nothing, must still discover something."""
        accounts = [AWSAccount(account_id="999999999999", account_name="unrelated")]
        with (
            patch(f"{MODULE}.boto3.Session", return_value=self._session()),
            patch.object(discovery, "_list_org_accounts", return_value=accounts),
            patch.object(discovery, "_discover_account"),
        ):
            topology = discovery.run()

        assert len(topology.accounts) == 1
        synthesized = topology.accounts[0]
        assert synthesized.account_id == "111111111111"
        assert synthesized.account_name == "management"
        assert synthesized.is_management_account is True

    def test_passes_the_role_name_not_the_full_arn(self, discovery):
        """org_role_arn is an ARN; _discover_account takes the bare role name."""
        accounts = [AWSAccount(account_id="123456789012", account_name="wanted")]
        with (
            patch(f"{MODULE}.boto3.Session", return_value=self._session()),
            patch.object(discovery, "_list_org_accounts", return_value=accounts),
            patch.object(discovery, "_discover_account") as discover,
        ):
            discovery.run()

        assert discover.call_args.args[1] == "CNA-ReadOnly"

    def test_discovers_every_account_in_the_org(self, discovery, opts):
        opts.account_ids = []
        accounts = [
            AWSAccount(account_id="111111111111", account_name="mgmt"),
            AWSAccount(account_id="222222222222", account_name="dev"),
            AWSAccount(account_id="333333333333", account_name="prod"),
        ]
        with (
            patch(f"{MODULE}.boto3.Session", return_value=self._session()),
            patch.object(discovery, "_list_org_accounts", return_value=accounts),
            patch.object(discovery, "_discover_account") as discover,
        ):
            topology = discovery.run()

        assert len(topology.accounts) == 3
        assert discover.call_count == 3

    def test_retries_the_caller_identity_call_on_rate_limit(self, discovery):
        """run() wraps get_caller_identity in with_retry(); assert it actually retries.

        T-403's notes: assert on retry behaviour, not just the happy path — a
        `with_retry` contract bug in this path is what prompted the item.
        """
        session = MagicMock()
        session.client.return_value.get_caller_identity.side_effect = [
            CNARateLimitError("Throttling"),
            {"Account": "111111111111"},
        ]
        with (
            patch(f"{MODULE}.boto3.Session", return_value=session),
            patch.object(discovery, "_list_org_accounts", return_value=[]),
            patch.object(discovery, "_discover_account"),
            patch("cna.core.throttle.time.sleep") as sleep,
        ):
            topology = discovery.run()

        assert session.client.return_value.get_caller_identity.call_count == 2
        assert topology.management_account_id == "111111111111"
        assert sleep.call_count == 1

    def test_gives_up_after_the_retry_budget_is_exhausted(self, discovery):
        session = MagicMock()
        session.client.return_value.get_caller_identity.side_effect = CNARateLimitError(
            "Throttling"
        )
        with (
            patch(f"{MODULE}.boto3.Session", return_value=session),
            patch.object(discovery, "_discover_account"),
            patch("cna.core.throttle.time.sleep"),
            pytest.raises(CNARateLimitError),
        ):
            discovery.run()

    def test_propagates_an_auth_failure_rather_than_returning_empty(self, discovery):
        """The docstring promises CNAAuthError; a silent empty topology would be worse."""
        session = MagicMock()
        session.client.return_value.get_caller_identity.side_effect = CNAAuthError("bad creds")
        with (
            patch(f"{MODULE}.boto3.Session", return_value=session),
            patch.object(discovery, "_discover_account") as discover,
            pytest.raises(CNAAuthError),
        ):
            discovery.run()

        assert discover.call_count == 0


class TestRegionLookupEndpoint:
    """`_region_for_region_lookup()` — no hardcoded region (TODO.md T-404).

    `describe_regions()` has to be called against some enabled region before the
    region list is known. That endpoint used to be the literal "us-east-1" at the
    call site, which is wrong in the aws-us-gov and aws-cn partitions, where the
    region does not exist. It is now resolved, with the declared option as a last
    resort rather than a hardcoded value.
    """

    def test_prefers_the_sessions_own_configured_region(self, discovery):
        """AWS_REGION / profile / instance metadata is always right for the partition."""
        session = MagicMock()
        session.region_name = "us-gov-west-1"
        assert discovery._region_for_region_lookup(session) == "us-gov-west-1"

    def test_falls_back_to_the_first_requested_region(self, discovery):
        """No session region, but the caller named regions — use one of theirs."""
        session = MagicMock()
        session.region_name = None
        discovery.opts.regions = ["cn-north-1", "cn-northwest-1"]
        assert discovery._region_for_region_lookup(session) == "cn-north-1"

    def test_uses_the_declared_option_as_a_last_resort(self, discovery):
        session = MagicMock()
        session.region_name = None
        discovery.opts.regions = []
        assert discovery._region_for_region_lookup(session) == "us-east-1"

    def test_the_last_resort_is_overridable_for_other_partitions(self, store):
        """The point of declaring it: aws-us-gov and aws-cn callers can change it."""
        opts = DiscoveryOptions(
            org_role_arn="arn:aws-us-gov:iam::123456789012:role/CNA-ReadOnly",
            region_lookup_endpoint="us-gov-west-1",
        )
        d = AWSDiscovery(store=store, options=opts)
        session = MagicMock()
        session.region_name = None
        assert d._region_for_region_lookup(session) == "us-gov-west-1"

    def test_describe_regions_is_called_against_the_resolved_endpoint(self, discovery):
        """The resolved value must actually reach session.client()."""
        session = MagicMock()
        session.region_name = "eu-west-1"
        session.client.return_value.describe_regions.return_value = {
            "Regions": [{"RegionName": "eu-west-1"}]
        }
        discovery.opts.regions = []
        discovery._get_enabled_regions(session)
        assert session.client.call_args.kwargs["region_name"] == "eu-west-1"


class TestAccessDeniedAuditEvent:
    """`_discover_account()` access-denied path (TODO.md T-402).

    This path called `write_audit_event(engagement_id, "aws", event={...})`, but
    the method takes `(engagement_id, event)` — so "aws" bound to `event` and the
    keyword raised `TypeError: got multiple values for argument 'event'`. It fired
    whenever an account could not be assumed, which is routine in org-wide
    discovery. `ty` found it on its first run; the real store is used here rather
    than a MagicMock, because a mock accepts any signature and would not have
    caught it.
    """

    def test_records_the_event_instead_of_raising_typeerror(self, discovery, tmp_path):
        from cna.core.persistence import EngagementStore

        store = EngagementStore(data_dir=tmp_path)
        engagement_id = "test-20260305-0003"
        store.engagement_dir(engagement_id).mkdir(parents=True, exist_ok=True)
        discovery.store = store

        account = AWSAccount(account_id="222222222222", account_name="denied")
        topology = MagicMock()
        with patch.object(discovery, "_assume_role", side_effect=CNAAuthError("AssumeRole failed")):
            discovery._discover_account(account, "CNA-ReadOnly", topology, engagement_id)

        audit = store.engagement_dir(engagement_id) / store.AUDIT_LOG_FILE
        assert audit.is_file(), "access-denied path wrote no audit event"
        events = [json.loads(line) for line in audit.read_text().splitlines() if line.strip()]
        assert len(events) == 1
        assert events[0]["type"] == "access_denied"
        assert events[0]["cloud"] == "aws", "the cloud label must survive inside the event"
        assert events[0]["account"] == "222222222222"
        assert "AssumeRole failed" in events[0]["error"]
        assert "timestamp" in events[0]


class TestRegionCheckpointWrite:
    """`_discover_region` checkpoint write (TODO.md T-410).

    `write_discovery_checkpoint` takes
    `(engagement_id, platform, account_or_sub_id, data)`, but this call passed
    `account_id=` — not a parameter — while omitting the required one, raising
    `TypeError: got an unexpected keyword argument 'account_id'`. It sits inside
    the per-region loop, so the first region of the first account killed AWS
    discovery and no checkpoint was ever written. Azure's equivalent call was
    always correct.

    Uses a real `EngagementStore`: a `MagicMock` accepts any keyword and is the
    reason this survived, exactly as with the `write_audit_event` bug (T-402).
    """

    def test_writes_a_checkpoint_per_region(self, discovery, tmp_path):
        from cna.core.persistence import EngagementStore

        store = EngagementStore(data_dir=tmp_path)
        engagement_id = "test-20260305-0004"
        store.engagement_dir(engagement_id).mkdir(parents=True, exist_ok=True)
        discovery.store = store

        account = AWSAccount(account_id="123456789012", account_name="prod")
        topology = AWSTopology(engagement_id=engagement_id)
        region_topo = AWSRegionTopology(account_id="123456789012", region="us-east-1")

        with (
            patch.object(discovery, "_assume_role", return_value=MagicMock()),
            patch.object(discovery, "_get_enabled_regions", return_value=["us-east-1"]),
            patch.object(discovery, "_discover_region", return_value=region_topo),
        ):
            discovery._discover_account(account, "CNA-ReadOnly", topology, engagement_id)

        checkpoints = sorted(
            (store.engagement_dir(engagement_id) / store.DISCOVERY_DIR).glob("*.json")
        )
        assert checkpoints, "no checkpoint written for the discovered region"
        assert len(checkpoints) == 1
        # account_or_sub_id "aws_123456789012_us-east-1" is sanitised by the store:
        # "/" and "-" become "_", and the platform prefixes the filename.
        assert checkpoints[0].name == "aws_aws_123456789012_us_east_1.json"
        payload = json.loads(checkpoints[0].read_text())
        assert payload["region"] == "us-east-1"
        assert payload["account_id"] == "123456789012"
        assert topology.regions == [region_topo]
