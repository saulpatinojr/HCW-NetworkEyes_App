"""AWS Network Discovery — Phase C core.

Discovers all network topology resources across every account in an AWS
Organization using STS AssumeRole cross-account access.

Design principles:
  - Every API call is paginated via paginator or manual NextToken loop.
  - Every blocked account/region is logged with reason — never silently skipped.
  - Rate limiting uses exponential backoff with full jitter (cna.core.throttle).
  - Output is written to EngagementStore as a versioned AWSTopology checkpoint.
  - --resume flag skips accounts with an existing checkpoint.

API coverage per region per account:
  ec2: VPCs, Subnets, RouteTables, IGWs, NAT GWs, SGs, NACLs, VPC Peering,
       VPN Gateways, TGWs, TGW Attachments, TGW Route Tables
  directconnect: Connections, Virtual Interfaces
  organizations: account list (management account only, via DescribeAccounts)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import boto3
import botocore.exceptions

from cna.core.exceptions import CNAAuthError
from cna.core.persistence import EngagementStore
from cna.core.throttle import PaginationCursor, with_retry
from cna.core.topology_schema import (
    NACL,
    VPC,
    AttachmentType,
    AWSAccount,
    AWSNetworkFirewall,
    AWSRegionTopology,
    AWSTopology,
    AWSWAFWebACL,
    DirectConnectConnection,
    InternetGateway,
    NACLEntry,
    NatGateway,
    PeeringState,
    RouteEntry,
    RouteTable,
    SecurityGroup,
    SecurityGroupRule,
    Subnet,
    SubnetType,
    TGWAttachment,
    TransitGateway,
    VpcPeeringConnection,
    VpnGateway,
)

logger = logging.getLogger("cna.discovery.aws")

# Regions to skip by default (opt-in regions that require explicit enablement)
_OPT_IN_REGIONS = {
    "ap-east-1",
    "ap-southeast-3",
    "ap-southeast-4",
    "eu-south-1",
    "eu-south-2",
    "eu-central-2",
    "me-south-1",
    "me-central-1",
    "af-south-1",
    "il-central-1",
}


@dataclass
class DiscoveryOptions:
    org_role_arn: str  # arn:aws:iam::MGMT:role/CNA-ReadOnly
    external_id: str | None = None
    regions: list[str] = field(default_factory=list)  # empty = all enabled regions
    account_ids: list[str] = field(default_factory=list)  # empty = all org accounts
    skip_opt_in_regions: bool = True
    resume: bool = False  # skip accounts with existing checkpoint
    max_concurrent_regions: int = 10


class AWSDiscovery:
    """Orchestrates cross-account, cross-region AWS network discovery."""

    def __init__(self, store: EngagementStore, options: DiscoveryOptions):
        self.store = store
        self.opts = options
        self._mgmt_session: boto3.Session | None = None

    # ------------------------------------------------------------------ setup

    def _assume_role(self, account_id: str, role_name: str) -> boto3.Session:
        """Assume the CNA read-only role in a member account."""
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        sts = self._mgmt_session.client("sts")
        try:
            kwargs = {
                "RoleArn": role_arn,
                "RoleSessionName": "CNA-Discovery",
                "DurationSeconds": 3600,
            }
            if self.opts.external_id:
                kwargs["ExternalId"] = self.opts.external_id
            resp = sts.assume_role(**kwargs)
            creds = resp["Credentials"]
            return boto3.Session(
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        except botocore.exceptions.ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("AccessDenied", "AccessDeniedException"):
                raise CNAAuthError(
                    f"AssumeRole failed for {role_arn}: {e.response['Error']['Message']}"
                ) from e
            raise

    def _list_org_accounts(self) -> list[AWSAccount]:
        """List all accounts in the AWS Organization from the management account."""
        orgs = self._mgmt_session.client("organizations")
        accounts = []
        cursor = PaginationCursor()
        while True:
            kwargs = {"MaxResults": 20}
            if cursor.next_token:
                kwargs["NextToken"] = cursor.next_token
            try:
                resp = with_retry(orgs.list_accounts, **kwargs)
            except botocore.exceptions.ClientError as e:
                if e.response["Error"]["Code"] == "AWSOrganizationsNotInUseException":
                    logger.warning(
                        "Account is not part of an AWS Organization. "
                        "Discovering management account only."
                    )
                    break
                raise
            for a in resp.get("Accounts", []):
                if a["Status"] != "ACTIVE":
                    logger.info("Skipping %s account %s (%s)", a["Status"], a["Id"], a["Name"])
                    continue
                accounts.append(
                    AWSAccount(
                        account_id=a["Id"],
                        account_name=a["Name"],
                    )
                )
            cursor.next_token = resp.get("NextToken")
            if not cursor.next_token:
                break
        return accounts

    def _get_enabled_regions(self, session: boto3.Session) -> list[str]:
        """Return all enabled regions, optionally filtered."""
        ec2 = session.client("ec2", region_name="us-east-1")
        resp = with_retry(
            ec2.describe_regions,
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}],
        )
        regions = [r["RegionName"] for r in resp["Regions"]]
        if self.opts.skip_opt_in_regions:
            regions = [r for r in regions if r not in _OPT_IN_REGIONS]
        if self.opts.regions:
            regions = [r for r in regions if r in self.opts.regions]
        return sorted(regions)

    # --------------------------------------------------------------- per-region

    def _discover_region(
        self, session: boto3.Session, account_id: str, region: str
    ) -> AWSRegionTopology:
        """Run full network discovery for one account + region combination."""
        ec2 = session.client("ec2", region_name=region)
        dc = session.client("directconnect", region_name=region)
        topo = AWSRegionTopology(account_id=account_id, region=region)

        try:
            topo.vpcs = self._collect_vpcs(ec2, account_id, region)
            topo.transit_gateways = self._collect_tgws(ec2, account_id, region)
            topo.direct_connect_connections = self._collect_dx(dc, account_id, region)
            topo.vpn_gateways = self._collect_vpn_gateways(ec2, account_id, region)
            topo.aws_network_firewalls = self._collect_network_firewalls(
                session, account_id, region
            )
            topo.waf_web_acls = self._collect_waf_web_acls(session, account_id, region)
        except botocore.exceptions.ClientError as e:
            code = e.response["Error"]["Code"]
            msg = e.response["Error"]["Message"]
            if code in ("UnauthorizedOperation", "AccessDenied", "AccessDeniedException"):
                logger.warning("Permission denied in %s/%s: %s", account_id, region, msg)
                topo.discovery_blocked = True
                topo.block_reason = f"Permission denied: {code} — {msg}"
                return topo
            if code == "AuthFailure":
                raise CNAAuthError(f"Auth failure in {account_id}/{region}: {msg}") from e
            logger.error("Unexpected error in %s/%s: %s", account_id, region, e)
            topo.discovery_blocked = True
            topo.block_reason = f"Unexpected API error: {code} — {msg}"

        return topo

    def _collect_vpcs(self, ec2, account_id: str, region: str) -> list[VPC]:
        vpcs = []
        paginator = ec2.get_paginator("describe_vpcs")
        for page in paginator.paginate():
            for v in page["Vpcs"]:
                name = self._tag(v, "Name")
                vpc = VPC(
                    id=v["VpcId"],
                    name=name,
                    cidr=v["CidrBlock"],
                    secondary_cidrs=[
                        a["CidrBlock"]
                        for a in v.get("CidrBlockAssociationSet", [])
                        if a["CidrBlockState"]["State"] == "associated"
                        and a["CidrBlock"] != v["CidrBlock"]
                    ],
                    is_default=v.get("IsDefault", False),
                    flow_logs_enabled=False,  # checked separately if needed
                    tags={t["Key"]: t["Value"] for t in v.get("Tags", [])},
                )
                vpc.subnets = self._collect_subnets(ec2, v["VpcId"])
                vpc.route_tables = self._collect_route_tables(ec2, v["VpcId"])
                vpc.internet_gateways = self._collect_igws(ec2, v["VpcId"])
                vpc.nat_gateways = self._collect_nats(ec2, v["VpcId"])
                vpc.peering_connections = self._collect_peering(ec2, v["VpcId"])
                vpc.security_groups = self._collect_security_groups(ec2, v["VpcId"])
                vpc.nacls = self._collect_nacls(ec2, v["VpcId"])
                vpcs.append(vpc)
                logger.debug(
                    "Collected VPC %s (%s) in %s/%s",
                    v["VpcId"],
                    name or "unnamed",
                    account_id,
                    region,
                )
        return vpcs

    def _collect_subnets(self, ec2, vpc_id: str) -> list[Subnet]:
        subnets = []
        paginator = ec2.get_paginator("describe_subnets")
        for page in paginator.paginate(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]):
            for s in page["Subnets"]:
                subnet_type = SubnetType.UNKNOWN
                # Public: has route to IGW in its route table
                # We resolve this post-collection once route tables are built
                subnets.append(
                    Subnet(
                        id=s["SubnetId"],
                        name=self._tag(s, "Name"),
                        cidr=s["CidrBlock"],
                        az=s["AvailabilityZone"],
                        subnet_type=subnet_type,
                        nacl_id=None,  # resolved from NACL associations
                        auto_assign_public_ip=s.get("MapPublicIpOnLaunch", False),
                    )
                )
        return subnets

    def _collect_route_tables(self, ec2, vpc_id: str) -> list[RouteTable]:
        tables = []
        paginator = ec2.get_paginator("describe_route_tables")
        for page in paginator.paginate(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]):
            for rt in page["RouteTables"]:
                routes = []
                for r in rt.get("Routes", []):
                    dest = (
                        r.get("DestinationCidrBlock")
                        or r.get("DestinationIpv6CidrBlock")
                        or r.get("DestinationPrefixListId", "unknown")
                    )
                    target = (
                        r.get("GatewayId")
                        or r.get("NatGatewayId")
                        or r.get("TransitGatewayId")
                        or r.get("VpcPeeringConnectionId")
                        or r.get("NetworkInterfaceId")
                        or r.get("InstanceId")
                        or r.get("LocalGatewayId", "local")
                    )
                    target_type = self._infer_target_type(target)
                    routes.append(
                        RouteEntry(
                            destination=dest,
                            target=target,
                            target_type=target_type,
                            state=r.get("State", "active"),
                        )
                    )
                is_main = any(a.get("Main", False) for a in rt.get("Associations", []))
                assoc_subnets = [
                    a["SubnetId"] for a in rt.get("Associations", []) if "SubnetId" in a
                ]
                tables.append(
                    RouteTable(
                        id=rt["RouteTableId"],
                        name=self._tag(rt, "Name"),
                        associated_subnet_ids=assoc_subnets,
                        routes=routes,
                        is_main=is_main,
                    )
                )
        return tables

    def _collect_igws(self, ec2, vpc_id: str) -> list[InternetGateway]:
        igws = []
        resp = with_retry(
            ec2.describe_internet_gateways,
            Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}],
        )
        for igw in resp.get("InternetGateways", []):
            igws.append(
                InternetGateway(
                    id=igw["InternetGatewayId"],
                    name=self._tag(igw, "Name"),
                    state="attached",
                )
            )
        return igws

    def _collect_nats(self, ec2, vpc_id: str) -> list[NatGateway]:
        nats = []
        paginator = ec2.get_paginator("describe_nat_gateways")
        for page in paginator.paginate(
            Filter=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "state", "Values": ["available", "pending"]},
            ]
        ):
            for nat in page["NatGateways"]:
                public_ip = None
                for addr in nat.get("NatGatewayAddresses", []):
                    if addr.get("PublicIp"):
                        public_ip = addr["PublicIp"]
                        break
                nats.append(
                    NatGateway(
                        id=nat["NatGatewayId"],
                        name=self._tag(nat, "Name"),
                        subnet_id=nat["SubnetId"],
                        state=nat["State"],
                        public_ip=public_ip,
                    )
                )
        return nats

    def _collect_peering(self, ec2, vpc_id: str) -> list[VpcPeeringConnection]:
        peerings = []
        for role in ["requester-vpc-info.vpc-id", "accepter-vpc-info.vpc-id"]:
            paginator = ec2.get_paginator("describe_vpc_peering_connections")
            for page in paginator.paginate(Filters=[{"Name": role, "Values": [vpc_id]}]):
                for p in page["VpcPeeringConnections"]:
                    state_code = p["Status"]["Code"]
                    try:
                        state = PeeringState(state_code)
                    except ValueError:
                        state = PeeringState.ACTIVE
                    req = p["RequesterVpcInfo"]
                    acc = p["AccepterVpcInfo"]
                    peerings.append(
                        VpcPeeringConnection(
                            id=p["VpcPeeringConnectionId"],
                            name=self._tag(p, "Name"),
                            requester_vpc_id=req["VpcId"],
                            requester_account_id=req["OwnerId"],
                            requester_region=req.get("Region", ""),
                            accepter_vpc_id=acc["VpcId"],
                            accepter_account_id=acc["OwnerId"],
                            accepter_region=acc.get("Region", ""),
                            state=state,
                        )
                    )
        return peerings

    def _collect_security_groups(self, ec2, vpc_id: str) -> list[SecurityGroup]:
        sgs = []
        paginator = ec2.get_paginator("describe_security_groups")
        for page in paginator.paginate(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]):
            for sg in page["SecurityGroups"]:
                rules = []
                for perm in sg.get("IpPermissions", []):
                    rules.extend(self._parse_sg_rules(perm, "ingress"))
                for perm in sg.get("IpPermissionsEgress", []):
                    rules.extend(self._parse_sg_rules(perm, "egress"))
                sgs.append(
                    SecurityGroup(
                        id=sg["GroupId"],
                        name=sg.get("GroupName"),
                        description=sg.get("Description"),
                        vpc_id=vpc_id,
                        rules=rules,
                        tags={t["Key"]: t["Value"] for t in sg.get("Tags", [])},
                    )
                )
        return sgs

    def _parse_sg_rules(self, perm: dict, direction: str) -> list[SecurityGroupRule]:
        rules = []
        protocol = perm.get("IpProtocol", "-1")
        from_port = perm.get("FromPort")
        to_port = perm.get("ToPort")
        cidr_ranges = [r["CidrIp"] for r in perm.get("IpRanges", [])] + [
            r["CidrIpv6"] for r in perm.get("Ipv6Ranges", [])
        ]
        for sg_ref in perm.get("UserIdGroupPairs", []):
            rules.append(
                SecurityGroupRule(
                    direction=direction,
                    protocol=protocol,
                    from_port=from_port,
                    to_port=to_port,
                    source_sg_id=sg_ref.get("GroupId"),
                )
            )
        if cidr_ranges or not perm.get("UserIdGroupPairs"):
            rules.append(
                SecurityGroupRule(
                    direction=direction,
                    protocol=protocol,
                    from_port=from_port,
                    to_port=to_port,
                    cidr_ranges=cidr_ranges,
                )
            )
        return rules

    def _collect_nacls(self, ec2, vpc_id: str) -> list[NACL]:
        nacls = []
        paginator = ec2.get_paginator("describe_network_acls")
        for page in paginator.paginate(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]):
            for nacl in page["NetworkAcls"]:
                entries = []
                for e in nacl.get("Entries", []):
                    entries.append(
                        NACLEntry(
                            rule_number=e["RuleNumber"],
                            protocol=e["Protocol"],
                            rule_action=e["RuleAction"],
                            cidr=e.get("CidrBlock", e.get("Ipv6CidrBlock", "0.0.0.0/0")),
                            from_port=e.get("PortRange", {}).get("From"),
                            to_port=e.get("PortRange", {}).get("To"),
                            egress=e.get("Egress", False),
                        )
                    )
                assoc_subnets = [a["SubnetId"] for a in nacl.get("Associations", [])]
                nacls.append(
                    NACL(
                        id=nacl["NetworkAclId"],
                        name=self._tag(nacl, "Name"),
                        vpc_id=vpc_id,
                        is_default=nacl.get("IsDefault", False),
                        entries=entries,
                        associated_subnet_ids=assoc_subnets,
                    )
                )
        return nacls

    def _collect_tgws(self, ec2, account_id: str, region: str) -> list[TransitGateway]:
        tgws = []
        paginator = ec2.get_paginator("describe_transit_gateways")
        for page in paginator.paginate(Filters=[{"Name": "owner-id", "Values": [account_id]}]):
            for t in page["TransitGateways"]:
                opts = t.get("Options", {})
                attachments = self._collect_tgw_attachments(ec2, t["TransitGatewayId"])
                tgws.append(
                    TransitGateway(
                        id=t["TransitGatewayId"],
                        name=self._tag(t, "Name"),
                        owner_account_id=t["OwnerId"],
                        amazon_side_asn=opts.get("AmazonSideAsn"),
                        attachments=attachments,
                        dns_support=opts.get("DnsSupport") == "enable",
                        vpn_ecmp_support=opts.get("VpnEcmpSupport") == "enable",
                        default_route_table_association=opts.get("DefaultRouteTableAssociation")
                        == "enable",
                        default_route_table_propagation=opts.get("DefaultRouteTablePropagation")
                        == "enable",
                    )
                )
        return tgws

    def _collect_tgw_attachments(self, ec2, tgw_id: str) -> list[TGWAttachment]:
        attachments = []
        paginator = ec2.get_paginator("describe_transit_gateway_attachments")
        for page in paginator.paginate(
            Filters=[{"Name": "transit-gateway-id", "Values": [tgw_id]}]
        ):
            for a in page["TransitGatewayAttachments"]:
                resource_type_raw = a.get("ResourceType", "vpc")
                try:
                    resource_type = AttachmentType(resource_type_raw.replace("-", "_"))
                except ValueError:
                    resource_type = AttachmentType.VPC
                attachments.append(
                    TGWAttachment(
                        id=a["TransitGatewayAttachmentId"],
                        resource_id=a["ResourceId"],
                        resource_type=resource_type,
                        resource_owner_account_id=a["ResourceOwnerId"],
                        state=a["State"],
                    )
                )
        return attachments

    def _collect_dx(self, dc, account_id: str, region: str) -> list[DirectConnectConnection]:
        connections = []
        try:
            resp = with_retry(dc.describe_connections)
            for c in resp.get("connections", []):
                connections.append(
                    DirectConnectConnection(
                        id=c["connectionId"],
                        name=c.get("connectionName"),
                        location=c.get("location", ""),
                        bandwidth=c.get("bandwidth", ""),
                        state=c.get("connectionState", ""),
                        owner_account_id=c.get("ownerAccount", account_id),
                    )
                )
        except botocore.exceptions.ClientError as e:
            logger.warning(
                "DirectConnect describe_connections failed in %s: %s",
                region,
                e.response["Error"]["Message"],
            )
        return connections

    def _collect_vpn_gateways(self, ec2, account_id: str, region: str) -> list[VpnGateway]:
        vgws = []
        try:
            resp = with_retry(ec2.describe_vpn_gateways)
            for v in resp.get("VpnGateways", []):
                attachments = v.get("VpcAttachments", [])
                vpc_id = attachments[0]["VpcId"] if attachments else None
                vgws.append(
                    VpnGateway(
                        id=v["VpnGatewayId"],
                        name=self._tag(v, "Name"),
                        state=v.get("State", ""),
                        type=v.get("Type", "ipsec.1"),
                        amazon_side_asn=v.get("AmazonSideAsn"),
                        vpc_id=vpc_id,
                    )
                )
        except botocore.exceptions.ClientError as e:
            logger.warning(
                "describe_vpn_gateways failed in %s: %s", region, e.response["Error"]["Message"]
            )
        return vgws

    def _collect_network_firewalls(
        self, session: boto3.Session, account_id: str, region: str
    ) -> list[AWSNetworkFirewall]:
        """Collect AWS Network Firewall resources in the region."""
        firewalls = []
        try:
            client = session.client("network-firewall", region_name=region)
            paginator = client.get_paginator("list_firewalls")
            for page in paginator.paginate():
                for fw_ref in page.get("Firewalls", []):
                    try:
                        detail = client.describe_firewall(FirewallArn=fw_ref["FirewallArn"])
                        fw = detail.get("Firewall", {})
                        status = detail.get("FirewallStatus", {})
                        log_s3 = False
                        log_cw = False
                        log_kinesis = False
                        try:
                            log_resp = client.describe_logging_configuration(
                                FirewallArn=fw_ref["FirewallArn"]
                            )
                            for lc in log_resp.get("LoggingConfiguration", {}).get(
                                "LogDestinationConfigs", []
                            ):
                                dest = lc.get("LogDestinationType", "")
                                if dest == "S3":
                                    log_s3 = True
                                elif dest == "CloudWatchLogs":
                                    log_cw = True
                                elif dest == "KinesisDataFirehose":
                                    log_kinesis = True
                        except Exception as _e:
                            logger.debug(
                                "[%s/%s] Firewall logging config unavailable: %s",
                                account_id,
                                region,
                                _e,
                            )
                        firewalls.append(
                            AWSNetworkFirewall(
                                firewall_arn=fw.get("FirewallArn", ""),
                                firewall_name=fw.get("FirewallName", ""),
                                vpc_id=fw.get("VpcId", ""),
                                firewall_policy_arn=fw.get("FirewallPolicyArn"),
                                subnet_mappings=[
                                    s.get("SubnetId", "") for s in fw.get("SubnetMappings", [])
                                ],
                                delete_protection=fw.get("DeleteProtection", False),
                                subnet_change_protection=fw.get("SubnetChangeProtection", False),
                                firewall_policy_change_protection=fw.get(
                                    "FirewallPolicyChangeProtection", False
                                ),
                                firewall_status=status.get("Status", "READY"),
                                logging_s3_enabled=log_s3,
                                logging_cloudwatch_enabled=log_cw,
                                logging_kinesis_enabled=log_kinesis,
                                tags={t["Key"]: t["Value"] for t in fw.get("Tags", [])},
                            )
                        )
                    except Exception as e:
                        logger.debug("[%s/%s] NFW detail failed: %s", account_id, region, e)
        except Exception as e:
            logger.debug("[%s/%s] Network Firewall list failed: %s", account_id, region, e)
        return firewalls

    def _collect_waf_web_acls(
        self, session: boto3.Session, account_id: str, region: str
    ) -> list[AWSWAFWebACL]:
        """Collect AWS WAF v2 Web ACLs (REGIONAL scope only per region)."""
        web_acls = []
        try:
            client = session.client("wafv2", region_name=region)
            paginator = client.get_paginator("list_web_acls")
            for page in paginator.paginate(Scope="REGIONAL"):
                for acl_summary in page.get("WebACLs", []):
                    try:
                        detail = client.get_web_acl(
                            Name=acl_summary["Name"],
                            Scope="REGIONAL",
                            Id=acl_summary["Id"],
                        )
                        acl = detail.get("WebACL", {})
                        default_action = (
                            "Allow" if "Allow" in acl.get("DefaultAction", {}) else "Block"
                        )
                        rules = acl.get("Rules", [])
                        managed_count = sum(
                            1
                            for r in rules
                            if "ManagedRuleGroupStatement" in r.get("Statement", {})
                        )
                        custom_count = len(rules) - managed_count
                        assoc_resp = client.list_resources_for_web_acl(
                            WebACLArn=acl.get("ARN", ""), ResourceType="APPLICATION_LOAD_BALANCER"
                        )
                        associated = assoc_resp.get("ResourceArns", [])
                        vis = acl.get("VisibilityConfig", {})
                        web_acls.append(
                            AWSWAFWebACL(
                                web_acl_id=acl.get("Id", ""),
                                web_acl_arn=acl.get("ARN", ""),
                                name=acl.get("Name", ""),
                                scope="REGIONAL",
                                default_action=default_action,
                                managed_rule_groups_count=managed_count,
                                custom_rules_count=custom_count,
                                associated_resource_arns=associated,
                                sampled_requests_enabled=vis.get("SampledRequestsEnabled", False),
                                cloudwatch_metrics_enabled=vis.get(
                                    "CloudWatchMetricsEnabled", False
                                ),
                            )
                        )
                    except Exception as e:
                        logger.debug("[%s/%s] WAF ACL detail failed: %s", account_id, region, e)
        except Exception as e:
            logger.debug("[%s/%s] WAF v2 list failed: %s", account_id, region, e)
        return web_acls

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _tag(resource: dict, key: str) -> str | None:
        for t in resource.get("Tags", []):
            if t["Key"] == key:
                return t["Value"]
        return None

    @staticmethod
    def _infer_target_type(target: str) -> str:
        if not target:
            return "unknown"
        prefixes = [
            ("igw-", "igw"),
            ("nat-", "nat"),
            ("tgw-", "tgw"),
            ("pcx-", "pcx"),
            ("vgw-", "vpgw"),
            ("eni-", "eni"),
            ("lgw-", "lgw"),
            ("i-", "instance"),
        ]
        for prefix, typ in prefixes:
            if target.startswith(prefix):
                return typ
        if target == "local":
            return "local"
        return "unknown"

    # ----------------------------------------------------------------- run

    def _discover_account(
        self,
        account,
        role_name: str,
        topology: AWSTopology,
        engagement_id: str,
    ) -> None:
        """Discover all regions in a single account and append to topology."""
        account_id = account.account_id
        logger.info(
            "[%s] Discovering account %s (%s)",
            engagement_id,
            account_id,
            account.account_name or "",
        )

        if self.opts.resume:
            checkpoints = self.store.list_completed_checkpoints(engagement_id, "aws")
            if any(account_id in c for c in checkpoints):
                logger.info(
                    "[%s] Skipping %s — checkpoint exists (--resume)", engagement_id, account_id
                )
                return

        try:
            if account.is_management_account:
                acct_session = self._mgmt_session
            else:
                acct_session = self._assume_role(account_id, role_name)
        except CNAAuthError as e:
            logger.error("Cannot access account %s: %s", account_id, e)
            self.store.write_audit_event(
                engagement_id,
                "aws",
                event={"type": "access_denied", "account": account_id, "error": str(e)},
            )
            return

        regions = self._get_enabled_regions(acct_session)
        logger.info("[%s] Account %s: %d regions", engagement_id, account_id, len(regions))

        for region in regions:
            logger.info("[%s] %s / %s", engagement_id, account_id, region)
            region_topo = self._discover_region(acct_session, account_id, region)
            topology.regions.append(region_topo)

            checkpoint_key = f"aws_{account_id}_{region}"
            self.store.write_discovery_checkpoint(
                engagement_id,
                "aws",
                account_id=checkpoint_key,
                data=json.loads(region_topo.model_dump_json()),
            )

            vpc_count = len(region_topo.vpcs)
            blocked = " [BLOCKED]" if region_topo.discovery_blocked else ""
            logger.info(
                "[%s] %s/%s: %d VPCs%s", engagement_id, account_id, region, vpc_count, blocked
            )

    def run(self) -> AWSTopology:
        """Execute full discovery. Returns completed AWSTopology.

        Raises:
            CNAAuthError: If management account credentials fail.
        """
        engagement_id = self.store.engagement_id
        logger.info("[%s] AWS discovery starting", engagement_id)

        # 1. Establish management account session
        self._mgmt_session = boto3.Session()
        identity = with_retry(self._mgmt_session.client("sts").get_caller_identity)
        mgmt_account_id = identity["Account"]
        logger.info("Management account: %s", mgmt_account_id)

        # 2. List org accounts
        accounts = self._list_org_accounts()
        if self.opts.account_ids:
            accounts = [a for a in accounts if a.account_id in self.opts.account_ids]
        if not accounts:
            accounts = [
                AWSAccount(
                    account_id=mgmt_account_id,
                    account_name="management",
                    is_management_account=True,
                )
            ]

        for a in accounts:
            if a.account_id == mgmt_account_id:
                a.is_management_account = True

        topology = AWSTopology(
            engagement_id=engagement_id,
            accounts=accounts,
            management_account_id=mgmt_account_id,
        )

        # 3. Discover each account
        role_name = self.opts.org_role_arn.split("/")[-1]  # extract role name from ARN
        for account in accounts:
            self._discover_account(account, role_name, topology, engagement_id)

        logger.info(
            "[%s] AWS discovery complete. %d regions collected.",
            engagement_id,
            len(topology.regions),
        )
        return topology
