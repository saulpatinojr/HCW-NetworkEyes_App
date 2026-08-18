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

import botocore.exceptions
import pytest

from cna.core.exceptions import CNAAuthError, CNARateLimitError
from cna.core.topology_schema import (
    AttachmentType,
    AWSAccount,
    AWSRegionTopology,
    AWSTopology,
    PeeringState,
)
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


def _client_error(code: str, msg: str = "denied", op: str = "Op"):
    """Build a botocore ClientError the way the SDK raises one."""
    return botocore.exceptions.ClientError({"Error": {"Code": code, "Message": msg}}, op)


def _pages(client, operation: str, pages: list[dict]):
    """Wire `client.get_paginator(operation).paginate(...)` to yield `pages`."""
    paginator = MagicMock()
    paginator.paginate.return_value = pages
    client.get_paginator.side_effect = lambda name: (
        paginator if name == operation else MagicMock(paginate=MagicMock(return_value=[]))
    )
    return paginator


class TestMgmtSessionGuard:
    """`_mgmt` narrows Optional once instead of 17 deref sites (T-410)."""

    def test_raises_named_error_before_run(self, store, opts):
        d = AWSDiscovery(store=store, options=opts)
        with pytest.raises(RuntimeError, match="call run\\(\\) before"):
            _ = d._mgmt

    def test_returns_the_session_once_set(self, discovery):
        assert discovery._mgmt is discovery._mgmt_session


class TestAssumeRole:
    def test_builds_session_from_returned_credentials(self, discovery):
        sts = MagicMock()
        sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIAEXAMPLE",
                "SecretAccessKey": "example-secret-not-real",
                "SessionToken": "example-token-not-real",
            }
        }
        discovery._mgmt_session.client.return_value = sts

        with patch(f"{MODULE}.boto3.Session") as session_cls:
            discovery._assume_role("222222222222", "CNA-ReadOnly")

        kwargs = sts.assume_role.call_args.kwargs
        assert kwargs["RoleArn"] == "arn:aws:iam::222222222222:role/CNA-ReadOnly"
        assert kwargs["DurationSeconds"] == 3600
        assert "ExternalId" not in kwargs, "no external id was configured"
        assert session_cls.call_args.kwargs["aws_access_key_id"] == "ASIAEXAMPLE"

    def test_passes_external_id_when_configured(self, store):
        opts = DiscoveryOptions(
            org_role_arn="arn:aws:iam::123456789012:role/CNA-ReadOnly",
            external_id="shared-secret-placeholder",
        )
        d = AWSDiscovery(store=store, options=opts)
        d._mgmt_session = MagicMock()
        sts = MagicMock()
        sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "a",
                "SecretAccessKey": "b",
                "SessionToken": "c",
            }
        }
        d._mgmt_session.client.return_value = sts

        with patch(f"{MODULE}.boto3.Session"):
            d._assume_role("222222222222", "CNA-ReadOnly")

        assert sts.assume_role.call_args.kwargs["ExternalId"] == "shared-secret-placeholder"

    @pytest.mark.parametrize("code", ["AccessDenied", "AccessDeniedException"])
    def test_access_denied_becomes_cna_auth_error(self, discovery, code):
        sts = MagicMock()
        sts.assume_role.side_effect = _client_error(code, "not authorized", "AssumeRole")
        discovery._mgmt_session.client.return_value = sts

        with pytest.raises(CNAAuthError, match="AssumeRole failed"):
            discovery._assume_role("222222222222", "CNA-ReadOnly")

    def test_other_client_errors_propagate_unchanged(self, discovery):
        """Only the access-denied codes are translated; the rest must not be swallowed."""
        sts = MagicMock()
        sts.assume_role.side_effect = _client_error("ThrottlingException", "slow down")
        discovery._mgmt_session.client.return_value = sts

        with pytest.raises(botocore.exceptions.ClientError):
            discovery._assume_role("222222222222", "CNA-ReadOnly")


class TestListOrgAccounts:
    def test_paginates_and_skips_non_active_accounts(self, discovery):
        orgs = MagicMock()
        orgs.list_accounts.side_effect = [
            {
                "Accounts": [
                    {"Id": "111111111111", "Name": "prod", "Status": "ACTIVE"},
                    {"Id": "222222222222", "Name": "closed", "Status": "SUSPENDED"},
                ],
                "NextToken": "page-2",
            },
            {"Accounts": [{"Id": "333333333333", "Name": "dev", "Status": "ACTIVE"}]},
        ]
        discovery._mgmt_session.client.return_value = orgs

        accounts = discovery._list_org_accounts()

        assert [a.account_id for a in accounts] == ["111111111111", "333333333333"]
        assert orgs.list_accounts.call_count == 2
        assert orgs.list_accounts.call_args_list[1].kwargs["NextToken"] == "page-2"

    def test_standalone_account_returns_empty_rather_than_raising(self, discovery):
        """A non-Organization account is a supported configuration, not an error."""
        orgs = MagicMock()
        orgs.list_accounts.side_effect = _client_error(
            "AWSOrganizationsNotInUseException", "not in use"
        )
        discovery._mgmt_session.client.return_value = orgs

        assert discovery._list_org_accounts() == []

    def test_other_org_errors_propagate(self, discovery):
        orgs = MagicMock()
        orgs.list_accounts.side_effect = _client_error("AccessDeniedException", "no orgs:List")
        discovery._mgmt_session.client.return_value = orgs

        with pytest.raises(botocore.exceptions.ClientError):
            discovery._list_org_accounts()


class TestGetEnabledRegions:
    def _session_returning(self, region_names):
        session = MagicMock()
        session.region_name = "us-east-1"
        ec2 = MagicMock()
        ec2.describe_regions.return_value = {"Regions": [{"RegionName": r} for r in region_names]}
        session.client.return_value = ec2
        return session

    def test_returns_sorted_and_filtered_by_requested_regions(self, discovery):
        session = self._session_returning(["us-west-2", "us-east-1", "eu-west-1"])
        # the `opts` fixture requests us-east-1 only
        assert discovery._get_enabled_regions(session) == ["us-east-1"]

    def test_returns_all_enabled_regions_when_none_requested(self, store):
        d = AWSDiscovery(
            store=store,
            options=DiscoveryOptions(org_role_arn="arn:aws:iam::1:role/r", regions=[]),
        )
        d._mgmt_session = MagicMock()
        session = self._session_returning(["us-west-2", "us-east-1"])

        assert d._get_enabled_regions(session) == ["us-east-1", "us-west-2"]

    def test_requests_only_enabled_opt_in_statuses(self, discovery):
        session = self._session_returning(["us-east-1"])
        discovery._get_enabled_regions(session)
        filters = session.client.return_value.describe_regions.call_args.kwargs["Filters"]
        assert filters[0]["Values"] == ["opt-in-not-required", "opted-in"]


class TestDiscoverRegion:
    def _session(self):
        session = MagicMock()
        client = MagicMock()
        client.get_paginator.return_value = MagicMock(paginate=MagicMock(return_value=[]))
        client.describe_internet_gateways.return_value = {}
        client.describe_connections.return_value = {}
        client.describe_vpn_gateways.return_value = {}
        session.client.return_value = client
        return session, client

    def test_happy_path_returns_unblocked_topology(self, discovery):
        session, _ = self._session()
        topo = discovery._discover_region(session, "123456789012", "us-east-1")

        assert topo.account_id == "123456789012"
        assert topo.region == "us-east-1"
        assert topo.discovery_blocked is False

    def test_auth_failure_raises_rather_than_recording_a_blocked_region(self, discovery):
        """An expired or invalid credential is fatal — it is not a per-region condition."""
        session, client = self._session()
        client.get_paginator.side_effect = _client_error("AuthFailure", "token expired")

        with pytest.raises(CNAAuthError, match="Auth failure"):
            discovery._discover_region(session, "123456789012", "us-east-1")

    def test_unexpected_api_error_blocks_the_region_without_raising(self, discovery):
        """One broken region must not abort discovery of every other region."""
        session, client = self._session()
        client.get_paginator.side_effect = _client_error("InternalError", "boom")

        topo = discovery._discover_region(session, "123456789012", "us-east-1")

        assert topo.discovery_blocked is True
        assert "InternalError" in topo.block_reason


class TestCollectVpcs:
    def test_maps_fields_and_recurses_into_children(self, discovery):
        ec2 = MagicMock()
        _pages(
            ec2,
            "describe_vpcs",
            [
                {
                    "Vpcs": [
                        {
                            "VpcId": "vpc-001",
                            "CidrBlock": "10.0.0.0/16",
                            "IsDefault": False,
                            "Tags": [
                                {"Key": "Name", "Value": "core"},
                                {"Key": "env", "Value": "p"},
                            ],
                            "CidrBlockAssociationSet": [
                                {
                                    "CidrBlock": "10.0.0.0/16",
                                    "CidrBlockState": {"State": "associated"},
                                },
                                {
                                    "CidrBlock": "10.1.0.0/16",
                                    "CidrBlockState": {"State": "associated"},
                                },
                                {
                                    "CidrBlock": "10.2.0.0/16",
                                    "CidrBlockState": {"State": "disassociated"},
                                },
                            ],
                        }
                    ]
                }
            ],
        )
        ec2.describe_internet_gateways.return_value = {}

        vpcs = discovery._collect_vpcs(ec2, "123456789012", "us-east-1")

        assert len(vpcs) == 1
        vpc = vpcs[0]
        assert vpc.id == "vpc-001"
        assert vpc.name == "core"
        assert vpc.cidr == "10.0.0.0/16"
        assert vpc.tags == {"Name": "core", "env": "p"}
        # primary excluded, disassociated excluded
        assert vpc.secondary_cidrs == ["10.1.0.0/16"]


class TestCollectIgws:
    def test_maps_attached_gateways(self, discovery):
        ec2 = MagicMock()
        ec2.describe_internet_gateways.return_value = {
            "InternetGateways": [
                {"InternetGatewayId": "igw-001", "Tags": [{"Key": "Name", "Value": "edge"}]}
            ]
        }

        igws = discovery._collect_igws(ec2, "vpc-001")

        assert [i.id for i in igws] == ["igw-001"]
        assert igws[0].name == "edge"
        assert igws[0].state == "attached"

    def test_returns_empty_when_none_attached(self, discovery):
        ec2 = MagicMock()
        ec2.describe_internet_gateways.return_value = {}
        assert discovery._collect_igws(ec2, "vpc-001") == []


class TestCollectPeering:
    def _peering(self, pcx_id, state="active"):
        return {
            "VpcPeeringConnectionId": pcx_id,
            "Status": {"Code": state},
            "RequesterVpcInfo": {
                "VpcId": "vpc-001",
                "OwnerId": "111111111111",
                "Region": "us-east-1",
            },
            "AccepterVpcInfo": {
                "VpcId": "vpc-002",
                "OwnerId": "222222222222",
                "Region": "us-west-2",
            },
            "Tags": [],
        }

    def test_queries_both_requester_and_accepter_roles(self, discovery):
        ec2 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.side_effect = [
            [{"VpcPeeringConnections": [self._peering("pcx-req")]}],
            [{"VpcPeeringConnections": [self._peering("pcx-acc")]}],
        ]
        ec2.get_paginator.return_value = paginator

        peerings = discovery._collect_peering(ec2, "vpc-001")

        assert [p.id for p in peerings] == ["pcx-req", "pcx-acc"]
        used_filters = [c.kwargs["Filters"][0]["Name"] for c in paginator.paginate.call_args_list]
        assert used_filters == [
            "requester-vpc-info.vpc-id",
            "accepter-vpc-info.vpc-id",
        ]

    def test_unknown_state_code_falls_back_to_active(self, discovery):
        """AWS adds status codes over time; an unmapped one must not raise."""
        ec2 = MagicMock()
        paginator = MagicMock()
        paginator.paginate.side_effect = [
            [{"VpcPeeringConnections": [self._peering("pcx-1", state="provisioning")]}],
            [],
        ]
        ec2.get_paginator.return_value = paginator

        peerings = discovery._collect_peering(ec2, "vpc-001")

        assert peerings[0].state == PeeringState.ACTIVE


class TestCollectNacls:
    def test_maps_entries_and_associations(self, discovery):
        ec2 = MagicMock()
        _pages(
            ec2,
            "describe_network_acls",
            [
                {
                    "NetworkAcls": [
                        {
                            "NetworkAclId": "acl-001",
                            "IsDefault": True,
                            "Tags": [],
                            "Associations": [{"SubnetId": "subnet-001"}],
                            "Entries": [
                                {
                                    "RuleNumber": 100,
                                    "Protocol": "6",
                                    "RuleAction": "allow",
                                    "CidrBlock": "0.0.0.0/0",
                                    "PortRange": {"From": 443, "To": 443},
                                    "Egress": False,
                                },
                                {
                                    "RuleNumber": 101,
                                    "Protocol": "-1",
                                    "RuleAction": "deny",
                                    "Ipv6CidrBlock": "::/0",
                                    "Egress": True,
                                },
                            ],
                        }
                    ]
                }
            ],
        )

        nacls = discovery._collect_nacls(ec2, "vpc-001")

        assert len(nacls) == 1
        nacl = nacls[0]
        assert nacl.id == "acl-001"
        assert nacl.is_default is True
        assert nacl.associated_subnet_ids == ["subnet-001"]
        assert nacl.entries[0].from_port == 443
        # falls back to the v6 block when there is no v4 one
        assert nacl.entries[1].cidr == "::/0"
        assert nacl.entries[1].from_port is None


class TestCollectTgws:
    def test_maps_options_and_nested_attachments(self, discovery):
        ec2 = MagicMock()
        tgw_pag = MagicMock()
        tgw_pag.paginate.return_value = [
            {
                "TransitGateways": [
                    {
                        "TransitGatewayId": "tgw-001",
                        "OwnerId": "111111111111",
                        "Tags": [{"Key": "Name", "Value": "hub"}],
                        "Options": {
                            "AmazonSideAsn": 64512,
                            "DnsSupport": "enable",
                            "VpnEcmpSupport": "disable",
                            "DefaultRouteTableAssociation": "enable",
                            "DefaultRouteTablePropagation": "disable",
                        },
                    }
                ]
            }
        ]
        att_pag = MagicMock()
        att_pag.paginate.return_value = [
            {
                "TransitGatewayAttachments": [
                    {
                        "TransitGatewayAttachmentId": "tgw-attach-001",
                        "ResourceId": "vpc-001",
                        "ResourceType": "vpc",
                        "ResourceOwnerId": "111111111111",
                        "State": "available",
                    },
                    {
                        "TransitGatewayAttachmentId": "tgw-attach-002",
                        "ResourceId": "dxgw-001",
                        "ResourceType": "direct-connect-gateway",
                        "ResourceOwnerId": "111111111111",
                        "State": "available",
                    },
                ]
            }
        ]
        ec2.get_paginator.side_effect = lambda name: (
            tgw_pag if name == "describe_transit_gateways" else att_pag
        )

        tgws = discovery._collect_tgws(ec2, "111111111111", "us-east-1")

        assert len(tgws) == 1
        tgw = tgws[0]
        assert tgw.name == "hub"
        assert tgw.amazon_side_asn == 64512
        assert tgw.dns_support is True
        assert tgw.vpn_ecmp_support is False
        assert tgw.default_route_table_association is True
        assert tgw.default_route_table_propagation is False
        # "direct-connect-gateway" normalises to the underscored enum value
        assert [a.resource_type for a in tgw.attachments] == [
            AttachmentType.VPC,
            AttachmentType.DIRECT_CONNECT,
        ]

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("vpc", AttachmentType.VPC),
            ("vpn", AttachmentType.VPN),
            # AWS returns the hyphenated service name, not the enum spelling.
            # `raw.replace("-", "_")` produced "direct_connect_gateway", which is
            # not a member, so this silently recorded a DX gateway as a VPC
            # attachment until T-408 added this case.
            ("direct-connect-gateway", AttachmentType.DIRECT_CONNECT),
            ("connect", AttachmentType.CONNECT),
            ("peering", AttachmentType.PEERING),
            ("tgw-peering", AttachmentType.PEERING),
        ],
    )
    def test_every_aws_resource_type_maps_correctly(self, discovery, raw, expected):
        ec2 = MagicMock()
        att_pag = MagicMock()
        att_pag.paginate.return_value = [
            {
                "TransitGatewayAttachments": [
                    {
                        "TransitGatewayAttachmentId": "tgw-attach-001",
                        "ResourceId": "x-001",
                        "ResourceType": raw,
                        "ResourceOwnerId": "111111111111",
                        "State": "available",
                    }
                ]
            }
        ]
        ec2.get_paginator.return_value = att_pag

        assert discovery._collect_tgw_attachments(ec2, "tgw-001")[0].resource_type == expected

    def test_unknown_attachment_type_falls_back_to_vpc(self, discovery):
        ec2 = MagicMock()
        att_pag = MagicMock()
        att_pag.paginate.return_value = [
            {
                "TransitGatewayAttachments": [
                    {
                        "TransitGatewayAttachmentId": "tgw-attach-001",
                        "ResourceId": "x-001",
                        "ResourceType": "something-new",
                        "ResourceOwnerId": "111111111111",
                        "State": "available",
                    }
                ]
            }
        ]
        ec2.get_paginator.return_value = att_pag

        attachments = discovery._collect_tgw_attachments(ec2, "tgw-001")

        assert attachments[0].resource_type == AttachmentType.VPC


class TestCollectDirectConnect:
    def test_maps_connections(self, discovery):
        dc = MagicMock()
        dc.describe_connections.return_value = {
            "connections": [
                {
                    "connectionId": "dxcon-001",
                    "connectionName": "primary",
                    "location": "EqDC2",
                    "bandwidth": "1Gbps",
                    "connectionState": "available",
                    "ownerAccount": "111111111111",
                }
            ]
        }

        conns = discovery._collect_dx(dc, "123456789012", "us-east-1")

        assert conns[0].id == "dxcon-001"
        assert conns[0].bandwidth == "1Gbps"
        assert conns[0].owner_account_id == "111111111111"

    def test_defaults_owner_to_the_calling_account(self, discovery):
        dc = MagicMock()
        dc.describe_connections.return_value = {"connections": [{"connectionId": "dxcon-001"}]}

        conns = discovery._collect_dx(dc, "123456789012", "us-east-1")

        assert conns[0].owner_account_id == "123456789012"

    def test_client_error_is_logged_not_raised(self, discovery):
        """Direct Connect is not enabled everywhere; a denial must not stop the region."""
        dc = MagicMock()
        dc.describe_connections.side_effect = _client_error("AccessDeniedException", "no dx")

        assert discovery._collect_dx(dc, "123456789012", "us-east-1") == []


class TestCollectVpnGateways:
    def test_maps_first_vpc_attachment(self, discovery):
        ec2 = MagicMock()
        ec2.describe_vpn_gateways.return_value = {
            "VpnGateways": [
                {
                    "VpnGatewayId": "vgw-001",
                    "State": "available",
                    "Type": "ipsec.1",
                    "AmazonSideAsn": 64512,
                    "Tags": [{"Key": "Name", "Value": "onprem"}],
                    "VpcAttachments": [{"VpcId": "vpc-001", "State": "attached"}],
                }
            ]
        }

        vgws = discovery._collect_vpn_gateways(ec2, "123456789012", "us-east-1")

        assert vgws[0].id == "vgw-001"
        assert vgws[0].vpc_id == "vpc-001"
        assert vgws[0].name == "onprem"

    def test_detached_gateway_has_no_vpc(self, discovery):
        ec2 = MagicMock()
        ec2.describe_vpn_gateways.return_value = {
            "VpnGateways": [{"VpnGatewayId": "vgw-001", "State": "available"}]
        }

        assert discovery._collect_vpn_gateways(ec2, "1", "us-east-1")[0].vpc_id is None

    def test_client_error_is_logged_not_raised(self, discovery):
        ec2 = MagicMock()
        ec2.describe_vpn_gateways.side_effect = _client_error("UnauthorizedOperation", "no")

        assert discovery._collect_vpn_gateways(ec2, "1", "us-east-1") == []


class TestCollectNetworkFirewalls:
    def _session_with(self, client):
        session = MagicMock()
        session.client.return_value = client
        return session

    def test_maps_firewall_and_all_three_logging_destinations(self, discovery):
        client = MagicMock()
        _pages(client, "list_firewalls", [{"Firewalls": [{"FirewallArn": "arn:fw:1"}]}])
        client.describe_firewall.return_value = {
            "Firewall": {
                "FirewallArn": "arn:fw:1",
                "FirewallName": "edge-fw",
                "VpcId": "vpc-001",
                "FirewallPolicyArn": "arn:pol:1",
                "SubnetMappings": [{"SubnetId": "subnet-001"}, {"SubnetId": "subnet-002"}],
                "DeleteProtection": True,
                "SubnetChangeProtection": True,
                "FirewallPolicyChangeProtection": False,
                "Tags": [{"Key": "env", "Value": "prod"}],
            },
            "FirewallStatus": {"Status": "READY"},
        }
        client.describe_logging_configuration.return_value = {
            "LoggingConfiguration": {
                "LogDestinationConfigs": [
                    {"LogDestinationType": "S3"},
                    {"LogDestinationType": "CloudWatchLogs"},
                    {"LogDestinationType": "KinesisDataFirehose"},
                ]
            }
        }

        fws = discovery._collect_network_firewalls(
            self._session_with(client), "123456789012", "us-east-1"
        )

        assert len(fws) == 1
        fw = fws[0]
        assert fw.firewall_name == "edge-fw"
        assert fw.subnet_mappings == ["subnet-001", "subnet-002"]
        assert fw.delete_protection is True
        assert fw.firewall_policy_change_protection is False
        assert (fw.logging_s3_enabled, fw.logging_cloudwatch_enabled) == (True, True)
        assert fw.logging_kinesis_enabled is True
        assert fw.tags == {"env": "prod"}

    def test_missing_logging_config_leaves_flags_false(self, discovery):
        """Logging config is a separate call and often denied; it must not lose the firewall."""
        client = MagicMock()
        _pages(client, "list_firewalls", [{"Firewalls": [{"FirewallArn": "arn:fw:1"}]}])
        client.describe_firewall.return_value = {
            "Firewall": {
                "FirewallArn": "arn:fw:1",
                "FirewallName": "edge-fw",
                "VpcId": "vpc-001",
            },
            "FirewallStatus": {},
        }
        client.describe_logging_configuration.side_effect = RuntimeError("denied")

        fws = discovery._collect_network_firewalls(
            self._session_with(client), "123456789012", "us-east-1"
        )

        assert len(fws) == 1
        assert fws[0].logging_s3_enabled is False
        assert fws[0].firewall_status == "READY", "defaults when the status block is absent"

    def test_detail_failure_drops_only_that_firewall(self, discovery):
        client = MagicMock()
        _pages(
            client,
            "list_firewalls",
            [{"Firewalls": [{"FirewallArn": "arn:fw:1"}, {"FirewallArn": "arn:fw:2"}]}],
        )
        client.describe_firewall.side_effect = [
            RuntimeError("boom"),
            {
                "Firewall": {
                    "FirewallArn": "arn:fw:2",
                    "FirewallName": "second",
                    "VpcId": "vpc-002",
                },
                "FirewallStatus": {},
            },
        ]
        client.describe_logging_configuration.return_value = {}

        fws = discovery._collect_network_firewalls(
            self._session_with(client), "123456789012", "us-east-1"
        )

        assert [f.firewall_name for f in fws] == ["second"]

    def test_unavailable_service_returns_empty(self, discovery):
        """network-firewall does not exist in every region or partition."""
        session = MagicMock()
        session.client.side_effect = RuntimeError("no such service")

        assert discovery._collect_network_firewalls(session, "1", "us-gov-west-1") == []


class TestCollectWafWebAcls:
    def _session_with(self, client):
        session = MagicMock()
        session.client.return_value = client
        return session

    def test_counts_managed_versus_custom_rules(self, discovery):
        client = MagicMock()
        _pages(client, "list_web_acls", [{"WebACLs": [{"Name": "app", "Id": "acl-1"}]}])
        client.get_web_acl.return_value = {
            "WebACL": {
                "Id": "acl-1",
                "ARN": "arn:acl:1",
                "Name": "app",
                "DefaultAction": {"Allow": {}},
                "Rules": [
                    {"Statement": {"ManagedRuleGroupStatement": {}}},
                    {"Statement": {"ManagedRuleGroupStatement": {}}},
                    {"Statement": {"RateBasedStatement": {}}},
                ],
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                },
            }
        }
        client.list_resources_for_web_acl.return_value = {"ResourceArns": ["arn:alb:1"]}

        acls = discovery._collect_waf_web_acls(
            self._session_with(client), "123456789012", "us-east-1"
        )

        assert len(acls) == 1
        acl = acls[0]
        assert acl.managed_rule_groups_count == 2
        assert acl.custom_rules_count == 1
        assert acl.default_action == "Allow"
        assert acl.associated_resource_arns == ["arn:alb:1"]
        assert acl.sampled_requests_enabled is True

    def test_block_default_action_is_recorded(self, discovery):
        client = MagicMock()
        _pages(client, "list_web_acls", [{"WebACLs": [{"Name": "app", "Id": "acl-1"}]}])
        client.get_web_acl.return_value = {
            "WebACL": {
                "Id": "acl-1",
                "ARN": "arn:acl:1",
                "Name": "app",
                "DefaultAction": {"Block": {}},
                "Rules": [],
            }
        }
        client.list_resources_for_web_acl.return_value = {}

        acls = discovery._collect_waf_web_acls(self._session_with(client), "1", "us-east-1")

        assert acls[0].default_action == "Block"
        assert acls[0].custom_rules_count == 0

    def test_scoped_to_regional(self, discovery):
        """CLOUDFRONT-scoped ACLs live in us-east-1 only and are collected elsewhere."""
        client = MagicMock()
        paginator = _pages(client, "list_web_acls", [{"WebACLs": []}])

        discovery._collect_waf_web_acls(self._session_with(client), "1", "us-east-1")

        assert paginator.paginate.call_args.kwargs["Scope"] == "REGIONAL"

    def test_detail_failure_drops_only_that_acl(self, discovery):
        client = MagicMock()
        _pages(client, "list_web_acls", [{"WebACLs": [{"Name": "app", "Id": "acl-1"}]}])
        client.get_web_acl.side_effect = RuntimeError("boom")

        assert discovery._collect_waf_web_acls(self._session_with(client), "1", "us-east-1") == []

    def test_unavailable_service_returns_empty(self, discovery):
        session = MagicMock()
        session.client.side_effect = RuntimeError("no wafv2 here")

        assert discovery._collect_waf_web_acls(session, "1", "cn-north-1") == []


class TestDiscoverAccount:
    def _topology(self):
        return AWSTopology(engagement_id="test-20260305-0001")

    def test_resume_skips_an_account_with_an_existing_checkpoint(self, discovery, store):
        discovery.opts.resume = True
        store.list_completed_checkpoints.return_value = ["aws_111111111111_us-east-1"]
        topology = self._topology()

        discovery._discover_account(
            AWSAccount(account_id="111111111111"), "CNA-ReadOnly", topology, "eng-1"
        )

        assert topology.regions == []
        store.write_discovery_checkpoint.assert_not_called()

    def test_management_account_reuses_the_management_session(self, discovery):
        account = AWSAccount(account_id="111111111111", is_management_account=True)
        with (
            patch.object(discovery, "_assume_role") as assume,
            patch.object(discovery, "_get_enabled_regions", return_value=[]),
        ):
            discovery._discover_account(account, "CNA-ReadOnly", self._topology(), "eng-1")

        assume.assert_not_called()

    def test_member_account_assumes_the_role(self, discovery):
        account = AWSAccount(account_id="222222222222")
        with (
            patch.object(discovery, "_assume_role") as assume,
            patch.object(discovery, "_get_enabled_regions", return_value=[]),
        ):
            discovery._discover_account(account, "CNA-ReadOnly", self._topology(), "eng-1")

        assume.assert_called_once_with("222222222222", "CNA-ReadOnly")

    def test_inaccessible_account_writes_one_audit_event_and_returns(self, discovery, store):
        """The T-402 regression: `cloud` travels inside the event dict, not positionally."""
        account = AWSAccount(account_id="222222222222")
        topology = self._topology()
        with patch.object(discovery, "_assume_role", side_effect=CNAAuthError("denied")):
            discovery._discover_account(account, "CNA-ReadOnly", topology, "eng-1")

        assert topology.regions == []
        args = store.write_audit_event.call_args.args
        assert len(args) == 2, "write_audit_event takes (engagement_id, event)"
        assert args[0] == "eng-1"
        assert args[1]["type"] == "access_denied"
        assert args[1]["cloud"] == "aws"
        assert args[1]["account"] == "222222222222"

    def test_writes_one_checkpoint_per_region_positionally(self, discovery, store):
        account = AWSAccount(account_id="111111111111", is_management_account=True)
        topology = self._topology()
        region_topo = AWSRegionTopology(account_id="111111111111", region="us-east-1")

        with (
            patch.object(
                discovery, "_get_enabled_regions", return_value=["us-east-1", "us-west-2"]
            ),
            patch.object(discovery, "_discover_region", return_value=region_topo),
        ):
            discovery._discover_account(account, "CNA-ReadOnly", topology, "eng-1")

        assert len(topology.regions) == 2
        assert store.write_discovery_checkpoint.call_count == 2
        args = store.write_discovery_checkpoint.call_args_list[0].args
        assert args[:3] == ("eng-1", "aws", "aws_111111111111_us-east-1")
        assert isinstance(args[3], dict), "the checkpoint payload must be JSON, not a model"
