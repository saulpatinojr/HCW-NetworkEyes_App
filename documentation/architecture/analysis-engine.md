# Analysis Engine — Architecture

> Version: 1.0.0 | Status: Active | Date: 2026-03-05

---

## What This Engine Does

The analysis engine consumes topology checkpoints produced by the discovery engine
and produces a `FindingsReport` — a structured list of findings with observed state,
severity, framework mappings, and deduplication keys — written atomically to the
`EngagementStore` for consumption by the report generation engine.

Recommendations are produced by a strictly separate code path (`recommendation_engine.py`)
via MCP server calls, per DD-003. The analysis engine never writes recommendations.

---

## Pipeline

```
cna analyze --engagement-id <id> [--azure | --aws | --both]
        │
        ├─ 1. Load all discovery checkpoints from EngagementStore
        ├─ 2. Validate each topology against topology_schema TOPOLOGY_SCHEMA_VERSION
        ├─ 3. Per topology — run finding rules:
        │     ├─ AWS rules (11 implemented):
        │     │   default-vpc-exists, flow-logs-disabled, sg-open-ssh,
        │     │   sg-open-rdp, igw-non-public-subnet, tgw-default-route-table,
        │     │   dx-no-redundancy, vpc-no-dns-resolution, nacl-allows-all,
        │     │   vpc-peering-no-flow-logs, subnet-no-route-table
        │     └─ Azure rules (7 implemented):
        │         vnet-no-ddos, subnet-no-nsg, firewall-threat-intel-alert,
        │         er-no-redundancy, vnet-peering-gateway-transit-miscfg,
        │         vnet-no-dns-servers, subnet-no-service-endpoint
        ├─ 4. Each finding validated by ObservedStateEnforcer:
        │     ├─ Hedge pattern check (16 linguistic patterns)
        │     └─ Evidence linkage check (min 1 evidence_id required)
        ├─ 5. Deduplication: key = {finding_id}:{resource_id} — no duplicates written
        ├─ 6. CRITICAL findings trigger EscalationEngine before run completes (DD-016)
        └─ 7. FindingsReport written atomically to EngagementStore
```

---

## Findings Schema

Every finding written to the store must have:

| Field | Type | Required | Description |
|---|---|---|---|
| `finding_id` | str | ✅ | Rule identifier (e.g. `AWS-NET-001`) |
| `resource_id` | str | ✅ | Cloud resource identifier |
| `observed_state` | str | ✅ | Factual description — no hedging language |
| `severity` | Severity | ✅ | `CRITICAL / HIGH / MEDIUM / LOW` |
| `framework_mappings` | list | ✅ | Min 1 WAF pillar + control ID |
| `evidence_id` | list | ✅ | Min 1 reference to discovery checkpoint data |
| `recommendation_ids` | list | — | Populated by recommendation engine separately |

---

## MCP Router — Recommendations

After analysis completes, the recommendation engine calls the MCP router:

```
recommendation_engine.py
        │
        ├─ findings with severity HIGH or CRITICAL
        │     ├─ AWS findings → aws_mcp_client → awslabs/mcp AWS MCP Server
        │     └─ Azure findings → azure_mcp_client → Microsoft Azure MCP Server
        └─ recommendations appended to FindingsReport.recommendations[]
            (separate list — never mixed with observed findings)
```

---

## Escalation Engine

CRITICAL findings (severity=CRITICAL) trigger `EscalationEngine.escalate()` immediately,
before the analysis run completes:

- MS Teams notification (if `TEAMS_WEBHOOK_URL` is set)
- Audit log entry with finding ID, resource ID, engagement ID
- Finding flagged with `escalated=True` in the store

This implements DD-016: security-critical findings are never silently buried in the report.
