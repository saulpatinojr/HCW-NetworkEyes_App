# Discovery Engine — Architecture

> Version: 1.0.0 | Status: Active | Date: 2026-03-05

---

## What This Engine Does

The discovery engine is the first component that communicates with a live cloud environment.
It produces `AWSTopology` and `AzureTopology` Pydantic models (topology_schema v1.1.0)
written to the EngagementStore as verifiable, resumable checkpoints. All downstream
components — diagram generation, AI analysis, report generation — consume these models.

---

## AWS Discovery Flow

```
cna discover aws --engagement-id <id> --org-role arn:aws:iam::MGMT:role/CNA-ReadOnly
        │
        ├─ 1. STS GetCallerIdentity — validate management account creds
        ├─ 2. organizations:ListAccounts — enumerate all ACTIVE org accounts
        ├─ 3. Per account: STS AssumeRole → temporary session (1hr, ExternalId optional)
        ├─ 4. ec2:DescribeRegions — enumerate all enabled regions
        ├─ 5. Per region:
        │     ├─ ec2:DescribeVpcs (paginated)
        │     ├─ ec2:DescribeSubnets (paginated, filtered by VPC)
        │     ├─ ec2:DescribeRouteTables (paginated, filtered by VPC)
        │     ├─ ec2:DescribeInternetGateways (filtered by attachment)
        │     ├─ ec2:DescribeNatGateways (paginated, state=available|pending)
        │     ├─ ec2:DescribeVpcPeeringConnections (paginated, both sides)
        │     ├─ ec2:DescribeSecurityGroups (paginated, filtered by VPC)
        │     ├─ ec2:DescribeNetworkAcls (paginated, filtered by VPC)
        │     ├─ ec2:DescribeTransitGateways (paginated, owner filter)
        │     ├─ ec2:DescribeTransitGatewayAttachments (paginated)
        │     ├─ directconnect:DescribeConnections
        │     └─ ec2:DescribeVpnGateways
        ├─ 6. Write checkpoint: engagements/{id}/discovery/aws_{account}_{region}.json
        └─ 7. Audit log entry per access-denied event
```

---

## Azure Discovery Flow

```
cna discover azure --engagement-id <id> --tenant-id <tenant>
        │
        ├─ 1. DefaultAzureCredential (or ClientSecretCredential for SP)
        ├─ 2. ManagementGroups.list() — full MG hierarchy from tenant root
        ├─ 3. Subscriptions.list() — all ENABLED subscriptions in tenant
        ├─ 4. Per subscription:
        │     ├─ network.virtual_networks.list_all() — VNets + subnets + peerings
        │     ├─ network.virtual_wans.list() + virtual_hubs.list()
        │     ├─ network.azure_firewalls.list_all()
        │     ├─ network.application_gateways.list_all()
        │     ├─ private_dns.private_zones.list() + virtual_network_links
        │     └─ network.express_route_circuits.list_all()
        ├─ 5. Write checkpoint: engagements/{id}/discovery/azure_{sub_id}.json
        └─ 6. Blocked subscription logged with HTTP status + message
```

---

## Error Handling Matrix

| Condition | AWS Behavior | Azure Behavior |
|---|---|---|
| STS AssumeRole denied | `CNAAuthError` raised, account skipped, audit log entry | — |
| EC2 UnauthorizedOperation | `discovery_blocked=True`, reason recorded | — |
| HTTP 401/403 on subscription | — | `discovery_blocked=True`, reason recorded |
| Region opt-in required | Skipped by default (`--skip-opt-in-regions`) | N/A |
| Rate limit (ThrottlingException) | `with_retry()` — exponential backoff, 5 retries | Azure SDK retry policy |
| Interrupted mid-run | `--resume` skips completed checkpoints | `--resume` skips completed subscriptions |
| Organization API unavailable | Discovers management account only, logs warning | — |

---

## IAM / RBAC Requirements

### AWS — Required per member account

See `cna/modules/network/module.yaml` for the full permission list.
The role must exist in every member account with this trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"AWS": "arn:aws:iam::MANAGEMENT_ACCOUNT:role/CNA-ReadOnly"},
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": {"sts:ExternalId": "CNA-ENGAGEMENT-ID"}
    }
  }]
}
```

### Azure — Required at Management Group level

- **Reader** role at the root Management Group (inherited by all subscriptions)
- **Network Contributor** is NOT required — Reader is sufficient for all `list` and `read` operations
- For Private DNS: **Private DNS Zone Contributor** read access at subscription level
- For Management Groups: **Management Group Reader** at tenant root

See `documentation/client-packet/permission-grant-guide.md` for the
client-facing permission request template.

---

## Checkpoint Format

Each checkpoint is a JSON file written atomically to:
```
engagements/{engagement_id}/discovery/
  aws_{account_id}_{region}.json   ← AWSRegionTopology.model_dump_json()
  azure_{subscription_id}.json     ← AzureSubscriptionTopology.model_dump_json()
```

Checkpoint files are versioned via the `schema_version` field in the parent
Topology model. If the schema version in a checkpoint does not match the
current `TOPOLOGY_SCHEMA_VERSION`, the discovery engine will refuse to load
it and require a fresh discovery run for that account/subscription.

---

## Resume Behavior

`--resume` reads the list of completed checkpoints from `EngagementStore`
and skips any account+region (AWS) or subscription (Azure) that already
has a checkpoint file. This allows recovery from:

- Network interruptions mid-run
- Rate limit timeouts that exhaust the retry budget
- Operator-interrupted runs (`Ctrl+C`)
- Partial permission grants (some accounts accessible, others not)

Checkpoints are never overwritten by resume — they are skipped. To
re-discover an account, delete its checkpoint file and rerun without `--resume`.
