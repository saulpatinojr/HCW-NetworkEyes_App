# REFACTOR_APP.md: Cloud Network Assessment (NetworkEyes) App refactoring instructions

| Field | Value |
|---|---|
| Date | 2026-10-10 |
| Program | HCW App-to-AddOn initiative (Pair 3, NetworkEyes) |
| This repository | `saulpatinojr/HCW-NetworkEyes_App` — retired on 2026-09-18, **restored on 2026-10-10** by the owner's decision (the earlier core repository's lineage merged back here) |
| Implementation target | **this repository** (owner decision 2026-10-10; written for the earlier core repository, whose paths are identical here) |
| Evidence commit | `5d3b914` (last `main` commit before retirement, read with `git show` and `git ls-tree` only) |
| Downstream consumer | `saulpatinojr/HCW-NetworkEyes_AddOn` (lab build, id `network-assessment`) |

> **Owner decision 2026-10-10:** this repository is the implementation target. The paragraph that stood here said the repository was archived and the target was the earlier core repository; its lineage has since been merged back here, so every path below applies to this tree unchanged. **Owner decision 2026-10-25 (standalone):** this repository depends on no other repository, so every statement below about appliance repositories, a build manifest (`latest-build.json`, `.deployment-catalog/`) or a dispatch to other repositories is the 2026-10-10 plan as written and no longer applies: the record of a build is the digest table in the step summary of `200-build-images.yml` and the five digests in the `310` release notes (`CLAUDE.md`, *The image contract*).

**Where this file lives.** This plan is an allowed root document in this repository (`scripts/validate_documentation_model.py` lists it as optional) and is removed once its change sets have shipped. The earlier paragraph here described a "policy exception" written while the repository was retired and the Core was the target; that situation ended on 2026-10-10 (see the owner decision above), so the paragraph was removed on 2026-10-24 (ticket #250). Nothing for this repository is written in the earlier core repository, which is reference only (`CLAUDE.md`).

**Owner's Azure target decision (2026-10-09, `PLAN.md` owner decision 2), quoted:** "*App* = Azure Container Apps + user-assigned managed identity (Reader; + Cost Management Reader for Cloud Assessor) on a client subscription/RG, clients clone the repo, anonymous live results, no visitor credential. *AddOn* = the **same Docker image** in a `lab` edition on the Hostinger VPS: visitors upload an **Azure Resource Graph export** (JSON/CSV, 5 MB / 5,000 rows, Turnstile-gated, in-memory, TTL), mirroring the Azure Migrate lab model; restart erases everything."

**Upstream and downstream model.** The Core is upstream: it owns the engine, the rule corpus, discovery and the appliance build, and publishes the Python distribution `cna-azure-network-engine` (import name `cna_azure_network_engine`) plus the appliance image. The AddOn `HCW-NetworkEyes_AddOn` is downstream: until the wheel exists it carries an interim port of about 1,100 lines from `5d3b914` with per-file provenance headers and a root `PROVENANCE.md`; once the wheel is published it pins the exact version and deletes `src/network_assessment/{model,rules,classify}` (AddOn ADR-0001). The AddOn never gains an Azure credential path; the Core never gains an upload path.

## 1 Purpose

This document tells a Core maintainer what to change, file by file, so that:

1. One engine (model, rules, classifier, findings, Markdown and JSON report, Resource Graph normalizer) exists once, as an installable package with no Azure SDK in its base dependencies.
2. One root Dockerfile builds the `appliance` target (Container Apps, user-assigned managed identity, live Resource Graph refresh, no upload) and a build-only `lab` target that proves the engine installs and runs without any Azure SDK; the deployable lab build, its HTTP contract and its checks belong to the AddOn, which builds its own image on the published engine with the same Dockerfile pattern.
3. The security findings recorded at `5d3b914` are closed: unauthenticated API, plaintext service-principal secrets between tiers, Network Contributor advice for a read-only scan, scanner-host DNS resolution presented as client evidence, raw exception strings persisted.
4. The two overlapping Azure rule engines become one typed, versioned rule set with stable ids.
5. AWS code stops being a hard dependency of an Azure-only install.

In scope: change sets A to K (sections 6 and 7). Out of scope: redesign of `apps/cna-web`, the AI copilot and recommendation engines, the diagram and report engines beyond the Markdown/JSON renderers, the AWS appliance.

## 2 Current-state summary

Evidence at `5d3b914`, line counts from `git show <path> | wc -l`.

| Component | Path | Lines | What it is |
|---|---|---|---|
| Azure discovery | `cna/modules/network/discovery/azure_discovery.py` | 2,590 | Class `AzureDiscovery`; 15 ARM SDK collectors per subscription (`_discover_subscription`, line 402; the `_run(...)` loop at lines 445 to 462), then `_run_phase2_collectors` (line 476) for NVAs, BGP, observability, metrics, Front Door WAF and Defender |
| Topology model | `cna/core/topology_schema.py` | 1,010 | `TOPOLOGY_SCHEMA_VERSION = "1.3.0"` (line 32); AWS classes lines 64 to 313; Azure classes lines 315 to 1010; shared enums lines 38 to 62 |
| Rule Engine A | `cna/ai_engine/analysis_engine.py` | 1,750 | `AnalysisEngine` (line 146); rule ids `AZ-NET-001..019` (lines 66 to 84) and `AWS-NET-001..013` (lines 53 to 63, 85 to 86); typed `Finding` output; hedge-word enforcement in `_emit` (line 165); constructor takes `EngagementStore` (line 152) |
| Rule Engine B | `apps/cna-api/main.py` | 1,815 total | 17 `_check_*` functions at lines 195 to 1127 and `_topology_to_findings` at lines 1129 to 1173; untyped dicts, no rule ids, no hedge check; this is what the web product runs for Azure |
| Observed-state enforcer | `cna/ai_engine/observed_state_enforcer.py` | 76 | 16 hedge patterns, pure `re` |
| Findings schema | `cna/core/findings_schema.py` | 104 | `ObservedState(fact, evidence_ref)` (lines 30 to 32), `Finding` (line 53), `FindingsReport` (line 94) |
| BC/DR, FinOps, classifier | `cna/modules/network/analysis/{bcdr_signals,finops_signals,topology_classifier}.py` | 294, 365, 134 | `AZ-BCDR-001..005`, `AZ-COST-001..005` with a static price table, `vwan/hub_spoke/mesh/isolated` |
| Traffic taxonomy | `cna/core/finding_taxonomy.py` | 224 | `classify_traffic_direction`, mixed AWS and Azure id tables |
| File store | `cna/core/persistence.py` | 388 | `EngagementStore`, local disk engagement folders |
| Web tier | `apps/cna-web/` | about 19.7k TS lines | Next.js 16, next-auth (Entra), Prisma 6, 15 migrations, `CloudCredential.spSecretEnc` (`prisma/schema.prisma` line 217) |
| SP help modal | `apps/cna-web/components/ui/sp-help-modal.tsx` | 363 | Tells users to grant Network Contributor (lines 93, 176, 197, 209 to 211, 218 to 225) |
| Packaging | `pyproject.toml` | 182 | `cna 0.8.0b0`, `requires-python >=3.11` (line 9), `boto3` and seven `azure-*` packages in base deps, `enrichment` and `dev` extras, no `license` field |
| Images | `Dockerfile` (94), `apps/cna-api/Dockerfile` (99) | | `python:3.14-slim@sha256:cae66f2e...` pinned, uid 1001, pip removed, draw.io plus xvfb; OCI label `licenses="Proprietary"` at that commit (`Dockerfile` line 50; `Apache-2.0` since 2026-10-25, `REVIEW.md` R-020); API deps installed inline (lines 17 to 39) including `psycopg2-binary` and `boto3` |
| CI and release | `.github/workflows/{200-build-images,300-test-codebase,310-release-version,370-registry-cleanup}.yml` | 363 (200) | Docker Hub login with `secrets.DOCKERHUB_TOKEN` (200: lines 67 to 72), Scout by digest, `notify-appliances` dispatch (removed 2026-10-25); release on tags `v*.*.*` (310: line 16) |
| Build manifest | `.deployment-catalog/latest-build.json` | 13 | `sha-11eaa7e` tags for `cli, api, worker, web, migrator` under `docker.io/hybridcloudworks/img-ne-appliance-app`; no digests (the file was removed 2026-10-25) |
| Backlog | `TODO.md` (1,849), `REVIEW.md` (548), `CHANGELOG.md` (245) | | T-401 to T-419, T-501 to T-508; R-008 (line 328), R-009 (375), R-011 (469), R-012 (516) open; `[Unreleased]` at `CHANGELOG.md` line 10 |
| Vendored agent configuration | `.agents/`, `.claude/`, `.codex/`, `.kiro/` | about 52 MB | Not product code |
| Tests | `tests/unit/` (73 files), `tests/integration/` | | `test_azure_discovery.py` 2,333 lines of mocked SDK; no `tests/security/` directory |

**The two rule engines.** Engine A (`analysis_engine.py`) is typed, versioned, hedge-checked, and used only by the CLI `cna analyze` and by the API's AWS path. Engine B (`main.py` `_check_*`) is what `_run_azure_discovery` (line 1603) runs for every Azure job; it overlaps Engine A on DDoS, NSG, WAF and flow-log checks and adds 14 checks Engine A lacks (RDP/SSH from Internet, wildcard rules, default route to Internet, BGP propagation, custom DNS, WAF detection mode, Basic SKUs, VPN generation, connection status, pending private endpoints, no firewall, no Bastion, zone redundancy for App Gateway and Load Balancer). Its remaining checks (`_check_nvas`, `_check_bgp_gateway`, `_check_observability`, `_check_network_metrics`) depend on live collectors.

**Deployment at this commit.** Terraform was removed by T-504 (`TODO.md` line 1486; last copy at `8bb989d`). The per-cloud Terraform is not in this repository; whoever deploys the images owns it.

## 3 Target-state summary

```
HCW-NetworkEyes_App (upstream)
  packages/cna-azure-network-engine/  -> PyPI: cna-azure-network-engine (wheel)
    cna_azure_network_engine/{model, rules, classify, findings, report, normalize}   (base: pydantic only)
    cna_azure_network_engine/discovery/   ([azure] extra: resource_graph + live_bgp/metrics/diagnostics/cost/law)
  cna/ (monorepo package, depends on the engine; CLI, API, report and diagram engines unchanged in scope)
  Dockerfile  ARG EDITION=appliance|lab  -> appliance image docker.io/hybridcloudworks/img-ne-appliance-app, consumed by digest;
                                            lab target = CI boundary proof (engine without [azure]), never pushed
  .github/workflows/320-release-engine.yml  (tag engine-v*)
Azure appliance repo: one Consumption Container App (min 1 / max 1), UAMI, Reader + optional reader roles
  + custom "CNA Network BGP Reader"; timer-driven ARG refresh; no upload route.
HCW-NetworkEyes_AddOn (downstream): same Dockerfile pattern on the published wheel without [azure]; builds and
  ships docker.io/hybridcloudworks/hcw-addon-network-assessment (the lab build's HTTP contract lives there);
  visitors upload an ARG export; deletes its ported model/rules/classify once the wheel exists.
```

Package contract:

| Item | Value |
|---|---|
| Distribution name | `cna-azure-network-engine` `[REVIEW REQUIRED]` (PyPI name and trusted publishing, section 22) |
| Import name | `cna_azure_network_engine` |
| Base dependencies | `pydantic>=2.13,<3` only |
| Extras | `[azure]`: `azure-identity`, `azure-mgmt-resourcegraph`, `azure-mgmt-network`, `azure-mgmt-monitor<7`, `azure-monitor-query<3`, `azure-mgmt-costmanagement<5`, `azure-mgmt-loganalytics<15`, `azure-mgmt-security<8` (bounds as `pyproject.toml` lines 71 to 82 already justify) |
| `requires-python` | `>=3.14` (the images already run `python:3.14-slim`; CI already tests 3.14 at `300-test-codebase.yml` line 137) |
| Public symbols | `TOPOLOGY_MODEL_VERSION`, `RULES_VERSION`, `RULES`, `AzureTopology`, `AzureSubscriptionTopology`, `Finding`, `FindingsReport`, `ObservedState`, `evaluate(topology) -> FindingsReport`, `normalize_resource_graph(rows) -> AzureTopology`, `render_markdown(report)`, `render_json(report)`, `classify_topology(topology)` |
| Release tag | `engine-v<semver>` on the Core; image tags stay `v*.*.*` |

## 4 Constraints

1. Never weaken: the lab build's inability to hold a credential or an Azure SDK, the appliance's read-only roles and refusal of client secrets, the "not production" labels, and the observed-state discipline (`_emit` hedge check at `analysis_engine.py` line 165 must apply to every rule, including the ported Engine B checks).
2. No secrets, tokens, inventories of a real environment or real tenant or subscription ids in fixtures, tests or docs. Sample subscriptions are `00000000-0000-0000-0000-000000000001` and `...0002`.
3. Rule ids are never reused; a changed rule bumps its own `version`; live-only rules stay registered so the AddOn's `unknowns[]` list is stable.
4. The Core publishes images to Docker Hub only (`docker.io/hybridcloudworks/img-ne-appliance-app`), by digest, through the Docker OIDC connection (section 12). No GHCR.
5. The Core keeps its own `CLAUDE.md` rules for PRs, changelog and review; this document does not override them.
6. Owner-pasteable commands have no placeholders; both bash and PowerShell are given where the shells differ.
7. Every Microsoft Learn citation, role action name and compliance-framework control reference carries `[VERIFY]` until checked.
8. The appliance's Terraform is not in this repository (T-504); this document names the resources it must gain, and whoever deploys the appliance writes the files.

## 5 Architectural issues

| # | Issue | Evidence at `5d3b914` | Consequence |
|---|---|---|---|
| 1 | Two Azure rule engines | Engine A `cna/ai_engine/analysis_engine.py:639-1660`; Engine B `apps/cna-api/main.py:195-1173` | The web product's findings have no rule ids, no versions and no hedge check; the CLI's findings disagree with the web's |
| 2 | SDK-shaped models | `cna/core/topology_schema.py:315-1010` mirror ARM SDK objects; Resource Graph rows are camelCase `properties` with `{id}` references | No normalizer exists; an export cannot populate the model without new code |
| 3 | `EngagementStore` coupling | `analysis_engine.py:38,152`; `run()` reads `self.store.engagement_id` (line 1669 onward); discovery writes checkpoints through the store | The engine cannot be imported without the file store; the API re-implements rules instead of reusing it |
| 4 | Dead `use_resource_graph` | `azure_discovery.py:96` is set and never read; `_discover_subscription` (line 402) runs 15 ARM list calls per subscription | Minutes per subscription; one permission failure per collector; no cross-subscription query |
| 5 | Network Contributor advice | `sp-help-modal.tsx:93,176,197,209-211,218-225`; `main.py:1146`; while `.env.example:73` says Reader and `cna/modules/network/module.yaml:27-35` lists only `*/read` actions | Users grant a write role for a read-only scan; the code contradicts itself |
| 6 | Unauthenticated API | `main.py` imports no auth dependency (lines 8 to 40); every route is open; the deployment relies on internal ingress | Any workload in the environment can start discovery, publish portals or read jobs |
| 7 | Plaintext SP secrets between tiers | `main.py:1457` and `:1541` (`sp_client_secret`, "plaintext, decrypted by web layer"); `apps/cna-web/app/(dashboard)/engagements/[id]/discovery/actions.ts:34`; `azure_discovery.py:247` (`ClientSecretCredential`); Prisma `spSecretEnc` (`schema.prisma:217`) | A long-lived user-supplied secret is stored, decrypted and transmitted; the owner decision is managed identity only |
| 8 | Scanner-host DNS resolution | `azure_discovery.py:1080-1105` (`_validate_pe_dns`, `_socket.gethostbyname` at 1101) | Evidence describes the scanner's resolver, not the user's; findings based on it are not observed state |
| 9 | Raw exception strings persisted | `azure_discovery.py:441` (`topo.block_reason = str(e)`); `main.py:1704,1812` (`errorMessage=str(exc)`) | Hostnames, paths and SDK text reach the database and the UI |
| 10 | AWS entanglement | `topology_schema.py:64-313`; `analysis_engine.py` `_check_aws_*` (lines 198 to 638); `boto3` in base deps (`pyproject.toml:13`) and in the API image (`apps/cna-api/Dockerfile:30`); `cna/core/escalation_engine.py:9` | An Azure-only install carries boto3 and AWS rules; the lab boundary test cannot forbid `boto3` without an extra |
| 11 | 52 MB vendored agent configuration | `.agents/`, `.claude/`, `.codex/`, `.kiro/` | Every clone, image context and `ty` run pays for it; `pyproject.toml:109` already excludes it from type checking |
| 12 | No image digests recorded | The build record carried `sha-<7>` tags only (resolved 2026-10-25: the `tag-images` step summary and the `310` release notes carry the digests) | A consumer could not pin by digest from the record |

## 6 Required refactoring

| Set | Title | Priority | Summary |
|---|---|---|---|
| A | Split `topology_schema.py` | P1 | `cna/core/topology/{common,azure,aws}.py`; `topology_schema.py` becomes a deprecation shim for one release |
| B | Unify Engine A and Engine B | P2 | Port the 14 Engine-B-only checks as typed rules `AZ-NET-020..033`, `AZ-BCDR-006/007`; delete `_check_*` and `_topology_to_findings` from `main.py` |
| C | Extract the engine package | P1 | `packages/cna-azure-network-engine/` with base and `[azure]` extra; the monorepo `cna` depends on it |
| D | Resource Graph discovery | P2 | Real `use_resource_graph`; one paged KQL query per scope replaces the 15-collector ARM loop; ARM only for BGP, metrics, diagnostics, cost, LAW; remove `socket.gethostbyname` |
| E | Engine independence from `EngagementStore` and Postgres | P1 | `evaluate(topology) -> FindingsReport` pure; store writes move to callers |
| F | Least-privilege roles | P1 (security) | Replace Network Contributor in four places; custom role JSON `docs/roles/cna-network-bgp-reader.json` |
| G | Appliance on Container Apps with UAMI; remove SP secrets | P1 (security) | Delete `ClientSecretCredential`, `sp_client_secret`, `/discovery/test-connection`; Prisma migration drops `spSecretEnc` |
| H | API bearer auth and exception redaction | P1 (security) | Entra JWT validation on `cna-api`; redaction helper for persisted errors |
| I | Lab boundary image target and boundary test | P2 | `ARG EDITION=appliance|lab` in the root `Dockerfile`; the `lab` target is a build-only boundary proof, never pushed; `tests/security/test_lab_boundary.py`; the deployable lab build is the AddOn's image |
| J | Engine release workflow and image digests | P3 | `320-release-engine.yml`; digests in the `tag-images` step summary and the `310` release notes |
| K | AWS gating behind an extra | P3 | `aws` extra and `cna/aws/` subpackage; `boto3` leaves the base |

## 7 File-by-file implementation instructions

Each subsection: current behavior (line-cited at `5d3b914`), required behavior, exact change, then components affected, tests, acceptance, priority, dependencies and rollback.

### 7.A Split `topology_schema.py` (change set A)

**Current behavior.** `cna/core/topology_schema.py` (1,010 lines) holds `TOPOLOGY_SCHEMA_VERSION = "1.3.0"` (line 32), shared enums `SubnetType`, `AttachmentType`, `PeeringState` (lines 38 to 62), AWS classes `RouteEntry` to `AWSTopology` (lines 64 to 313) and Azure classes `AzureSubnet` to `AzureTopology` (lines 315 to 1010). `AWSTopology.schema_version` (line 304) and `AzureTopology.schema_version` (line 1006) share one version string.

**Required behavior.** Azure and AWS models live in separate modules with separate versions; the old import path keeps working for one release and warns.

**Exact change.** New `cna/core/topology/common.py` (the three enums), `azure.py` (lines 315 to 1010 verbatim, `AZURE_TOPOLOGY_VERSION = "1.3.0"`), `aws.py` (lines 64 to 313 verbatim, `AWS_TOPOLOGY_VERSION = "1.3.0"`), `__init__.py` re-exporting common and azure. `cna/core/topology_schema.py` becomes:

```python
"""Deprecated: import from cna.core.topology.azure / .aws / .common instead."""
import warnings
from cna.core.topology.common import *  # noqa: F401,F403
from cna.core.topology.azure import *   # noqa: F401,F403
from cna.core.topology.aws import *     # noqa: F401,F403
from cna.core.topology.azure import AZURE_TOPOLOGY_VERSION as TOPOLOGY_SCHEMA_VERSION  # noqa: F401
warnings.warn("cna.core.topology_schema is deprecated; import cna.core.topology.azure or .aws", DeprecationWarning, stacklevel=2)
```

Update imports in `azure_discovery.py`, `analysis_engine.py`, `bcdr_signals.py`, `finops_signals.py`, `topology_classifier.py`, `apps/cna-api/main.py` (line 37 block), `cna/core/stat_masters.py`, the diagram engine and `tests/unit/test_topology_models.py`.

- **Components affected.** `cna/core`, `cna/modules/network`, `cna/ai_engine`, `apps/cna-api`, `cna/diagram_engine`, tests.
- **Tests.** `tests/unit/test_topology_models.py` imports from both paths; a new test asserts `python -W error -c "import cna.core.topology_schema"` raises `DeprecationWarning`; `tests/unit/test_azure_discovery.py` passes unchanged after the import rewrite.
- **Acceptance.** `git grep -l "from cna.core.topology_schema" -- cna apps` returns only `cna/core/topology_schema.py`; `cna/core/topology/azure.py` imports nothing from `aws.py`.
- **Priority** P1. **Dependencies** none. **Rollback** the shim keeps every old import working; the import rewrite is a plain `git revert`.

### 7.B Unify Engine A and Engine B (change set B)

**Current behavior.** `apps/cna-api/main.py:195-1127` defines `_check_no_firewall`, `_check_vnet`, `_check_nsg`, `_check_route_tables`, `_check_firewalls`, `_check_app_gateways`, `_check_load_balancers`, `_check_vnet_gateway_connections`, `_check_public_ips`, `_check_bastion`, `_check_private_endpoints`, `_check_gateway_skus`, `_check_nva`, `_check_nvas`, `_check_bgp_gateway`, `_check_observability`, `_check_network_metrics`; `_topology_to_findings` (lines 1129 to 1173) chains them over a `dict` topology and returns untyped dicts. `_finding_model_to_dict` (line 1176) already maps a typed `Finding` to the Prisma shape and embeds the rule id in the title because "The Prisma Finding table has no ruleId column". `_PLATFORM_SUBNETS` (lines 186 to 192) is the skip list Engine A lacks.

**Required behavior.** One registry of typed rules; Engine B's unique logic becomes rules with ids, severities, versions, framework mappings and learn URLs; `_run_azure_discovery` calls `evaluate()`; `main.py` carries no rule logic.

**Exact change.** New `cna/ai_engine/azure_rules/` (moved into the engine package by change set C):

```python
# cna/ai_engine/azure_rules/registry.py
RULES_VERSION = "2026.10.0"

@dataclass(frozen=True)
class RuleMeta:
    id: str; title: str; severity: FindingSeverity; category: str; version: int
    learn_url: str; frameworks: tuple[FrameworkMapping, ...]
    applies_to: Literal["export", "live-only"]; evidence: str

RULES: dict[str, tuple[RuleMeta, Callable[[AzureSubscriptionTopology, AzureTopology], Iterable[Finding]]]] = {}
def rule(**meta) -> Callable: ...   # registers (RuleMeta, fn); a duplicate id raises
def evaluate(topology: AzureTopology) -> FindingsReport: ...
    # runs every rule whose inputs are present, dedups on f"{rule_id}:{resource_id}", runs ObservedStateEnforcer
```

Rule mapping (ids, severities and evidence as the AddOn design table B.4; the Core and the AddOn must agree on these exactly):

| New rule | From `main.py` | Severity | Note |
|---|---|---|---|
| `AZ-NET-020` NSG allows RDP/SSH inbound from Internet | `_check_nsg` second loop (line 299 onward) | CRITICAL | ports 22/3389 incl. ranges |
| `AZ-NET-021` NSG wildcard allow-all | `_check_nsg` first loop | HIGH | |
| `AZ-NET-022` Route table default route to Internet | `_check_route_tables` (380) | MEDIUM | |
| `AZ-NET-023` BGP route propagation disabled | `_check_route_tables` | INFORMATIONAL | |
| `AZ-NET-024` VNet uses custom DNS servers | `_check_vnet` (216) | INFORMATIONAL | |
| `AZ-NET-025` App Gateway WAF in Detection mode | `_check_app_gateways` (468) | MEDIUM | |
| `AZ-NET-026` Load balancer Basic SKU | `_check_load_balancers` (524) | MEDIUM | retired 30 September 2025 (Microsoft Learn, checked 2026-10-25) |
| `AZ-NET-027` Public IP Basic SKU | `_check_public_ips` (612) | MEDIUM | one finding per IP, not per subscription |
| `AZ-NET-028` VPN gateway Basic SKU | `_check_gateway_skus` (703) | HIGH | |
| `AZ-NET-029` VPN gateway Generation1 | `_check_gateway_skus` | LOW | |
| `AZ-NET-030` Gateway connection not Connected | `_check_vnet_gateway_connections` (567) | HIGH | |
| `AZ-NET-031` Private endpoint connection Pending | `_check_private_endpoints` (678) | MEDIUM | |
| `AZ-NET-032` No Azure Firewall with VNets present | `_check_no_firewall` (195) | MEDIUM (B said HIGH) | suppressed by a secured vWAN hub or an NVA-shaped `0.0.0.0/0 -> VirtualAppliance` route |
| `AZ-NET-033` No Azure Bastion with VNets present | `_check_bastion` (656) | LOW (B said MEDIUM) | |
| `AZ-BCDR-006` App Gateway not zone-redundant | `_check_app_gateways` | MEDIUM | v2 SKUs with fewer than two zones |
| `AZ-BCDR-007` Standard LB not zone-redundant | `_check_load_balancers` | LOW | |
| `AZ-NET-002` v2 | Engine A `_check_azure_vnet` + `_PLATFORM_SUBNETS` | HIGH | merged skip list; `version` bumped to 2 |

`_check_nvas`, `_check_bgp_gateway`, `_check_observability`, `_check_network_metrics` fold into Engine A's existing live rules (`AZ-NET-008..010, 013, 015..017, 019`) where they overlap and are otherwise dropped with a changelog line; their inputs are `[azure]`-extra collectors after change set D. In `main.py`: delete lines 186 to 1173; in `_run_azure_discovery` (line 1603 onward) replace the `_topology_to_findings` call with `report = evaluate(topology_model)` and write through `_finding_model_to_dict`; the finops and bcdr generators (imported at line 33) become registered rules and are no longer called separately.

- **Components affected.** `apps/cna-api/main.py`, `cna/ai_engine/`, `cna/modules/network/analysis/`, `tests/unit/test_cna_api_worker_decision.py`, `tests/unit/test_cna_api_error_paths.py`; the web findings page reads `ruleId` from the title prefix, unchanged.
- **Tests.** `tests/unit/test_analysis_engine.py` stays green; new `tests/unit/rules/test_azure_net_020_033.py` and `test_azure_bcdr_006_007.py` with one fixture per rule; `tests/unit/test_registry.py` asserts unique ids, every rule has `learn_url` and at least one framework mapping, every title and description passes `ObservedStateEnforcer`, and `RULES_VERSION` changes when the id set changes (hash pinned).
- **Acceptance.** `git grep -c "def _check_" -- apps/cna-api/main.py` prints nothing or `0`; every finding written to Postgres carries a rule id; the web findings page shows ids for every finding.
- **Priority** P2. **Dependencies** A (model imports), E (pure `evaluate`). **Rollback** `git revert` of the `main.py` commit; the rules module is additive and harmless when unused.

### 7.C Extract the engine package (change set C)

**Current behavior.** The engine's pieces are spread across `cna/core`, `cna/ai_engine` and `cna/modules/network/analysis`, inside the `cna` distribution whose base dependencies include seven `azure-*` packages, `boto3`, `openai`, `anthropic`, `weasyprint` and `pandas` (`pyproject.toml:10-48`).

**Required behavior.** `pip install cna-azure-network-engine` in a clean venv installs `pydantic` only and exposes model, rules, classifier, findings, Markdown/JSON renderers and the Resource Graph normalizer. `pip install "cna-azure-network-engine[azure]"` adds discovery.

**Exact change.**

```
packages/cna-azure-network-engine/pyproject.toml   # name, requires-python >=3.14, dependencies = ["pydantic>=2.13,<3"], optional azure extra (section 3)
packages/cna-azure-network-engine/cna_azure_network_engine/
  __init__.py            # exports of section 3; __version__
  model/azure.py, model/common.py        # from cna/core/topology/{azure,common}.py (A); TOPOLOGY_MODEL_VERSION = "1.3.0"
  findings/schema.py     # findings_schema.py minus FindingRecommendation.source, recommendation_source, human_reviewed,
                         # human_notes, est_monthly_cost_usd; plus ObservedState.state (section 9)
  findings/enforcer.py   # observed_state_enforcer.py verbatim
  rules/{registry,azure_net,azure_bcdr,azure_cost,frameworks,taxonomy}.py   # from B, bcdr_signals, finops_signals, finding_taxonomy
  classify/topology.py   # topology_classifier.py
  report/markdown.py, report/jsonreport.py   # new: Markdown and JSON renderers only
  normalize/resource_graph.py  # new: rows -> AzureTopology (type table in the AddOn design B.3)
  discovery/             # change set D; imports azure.* lazily, guarded by the extra
packages/cna-azure-network-engine/tests/  # moved unit tests
```

Root `pyproject.toml` adds `"cna-azure-network-engine @ file://./packages/cna-azure-network-engine"` during the monorepo phase (an exact version once published); `cna/core/topology/azure.py`, `cna/ai_engine/observed_state_enforcer.py`, `cna/core/findings_schema.py` and the three analysis modules become one-line re-exports from the package. `cna/core/finding_taxonomy.py` keeps the AWS tables and re-exports the Azure part from `rules/taxonomy.py`.

- **Components affected.** Everything importing the moved modules; `apps/cna-api/Dockerfile` (install the package before `cna`); `300-test-codebase.yml` (package tests in a clean venv job).
- **Tests.** `tests/packaging/test_engine_wheel.py`: `uv build packages/cna-azure-network-engine`, install in a temporary venv, `python -c "import cna_azure_network_engine as e; assert e.RULES_VERSION"`, and `pip list` contains no `azure-*`, `boto3` or `psycopg2`.
- **Acceptance.** The packaging test passes; `python -c "import cna_azure_network_engine, sys; assert 'azure' not in sys.modules"` succeeds.
- **Priority** P1. **Dependencies** A. **Rollback** re-exports keep the old paths; deleting `packages/` and the dependency line restores `5d3b914` behaviour.

### 7.D Resource Graph discovery (change set D)

**Current behavior.** `AzureDiscoveryOptions.use_resource_graph: bool = True` (`azure_discovery.py:96`) is never read. `_discover_subscription` (line 402) creates `NetworkManagementClient` and `ResourceManagementClient`, lists resource groups, then runs 15 collectors (lines 445 to 462: `public_ips, nsgs, route_tables, nat_gateways, vnets, virtual_wans, route_servers, firewalls, application_gateways, load_balancers, virtual_network_gateways, private_endpoints, bastion_hosts, private_dns_zones, express_route_circuits`), then `_run_phase2_collectors` (line 476). `_validate_pe_dns` (lines 1080 to 1105) resolves the FQDNs of the assessed environment with `_socket.gethostbyname` from the scanner host.

**Required behavior.** One paged Resource Graph query per scope populates the model through the normalizer; ARM is used only where Resource Graph has no data (BGP POST actions, Monitor metrics, diagnostic settings, Cost Management, Log Analytics queries); the private-endpoint DNS check is removed and the field becomes `unknown`.

**Exact change.** New `cna_azure_network_engine/discovery/resource_graph.py`:

```python
NETWORK_QUERY = ("Resources | where type startswith 'microsoft.network/' "
                 "| project id, name, type, location, resourceGroup, subscriptionId, tags, zones, sku, kind, properties")
CONTAINERS_QUERY = "ResourceContainers | project id, name, type, properties"
DEFENDER_QUERY = "SecurityResources | where type == 'microsoft.security/assessments' | project id, name, properties"
NVA_QUERY = ("Resources | where type in~ ('microsoft.compute/virtualmachines','microsoft.network/networkinterfaces') "
             "| project id, name, type, location, resourceGroup, subscriptionId, properties, plan")

@dataclass(frozen=True)
class Scope:
    subscription_id: str
    resource_group: str | None      # lower-cased; None means the whole subscription

_SCOPE_RE = re.compile(r"^/subscriptions/(?P<sub>[0-9a-f-]{36})(?:/resourceGroups/(?P<rg>[^/]+))?/?$", re.IGNORECASE)

def parse_scopes(value: str) -> list[Scope]:
    """CNA_SCOPES, space-separated. Accepts /subscriptions/<sub> and /subscriptions/<sub>/resourceGroups/<rg>;
    anything else -> SystemExit at startup, before any query."""

def query_all(client, query: str, subscriptions: list[str], page: int = 1000) -> tuple[list[dict], bool]:
    """QueryRequest(subscriptions=subscriptions, query=query, options=QueryRequestOptions(top=page, skip_token=token));
    loop until skip_token is None. Returns (rows, truncated): truncated is True only when a token remained
    unconsumed (row cap reached or a page failed) or total_records exceeds len(rows)."""

def filter_to_scopes(rows: list[dict], scopes: list[Scope]) -> list[dict]:
    """Keep a row when its subscriptionId is in a whole-subscription scope, or when
    (subscriptionId, resourceGroup.lower()) matches a resource-group scope. Rows outside every scope are dropped."""

class ResourceGraphDiscovery:
    def __init__(self, credential, scopes: list[Scope], progress=None): ...
    def run(self) -> AzureTopology:
        subs = sorted({s.subscription_id for s in self.scopes})      # what Resource Graph is asked for
        rows, truncated = query_all(self._client, NETWORK_QUERY, subs)
        topology = normalize_resource_graph(filter_to_scopes(rows, self.scopes))
        attach_containers(topology, query_all(self._client, CONTAINERS_QUERY, subs)[0])
        attach_defender(topology, filter_to_scopes(query_all(self._client, DEFENDER_QUERY, subs)[0], self.scopes))
        attach_nvas(topology, filter_to_scopes(query_all(self._client, NVA_QUERY, subs)[0], self.scopes))
        if truncated:
            topology.warnings.append("resource graph response was truncated; findings cover the rows received")
        return topology
```

`run()` is the only caller of the four queries: `attach_defender` fills `AzureSubscriptionTopology.defender_assessments` (`DefenderAssessment`, `topology_schema.py:936`) and `attach_nvas` fills `nvas` and `nics` (`AzureNVA`, `AzureNIC`, lines 757 to 798), so the rules and report sections that read them (the NVA checks folded into the live rules under 7.B, the Defender posture summary in `report/markdown.py`) see the same model fields the ARM collectors filled.

`discovery/live_bgp.py`, `live_metrics.py`, `live_diagnostics.py`, `live_cost.py`, `live_law.py` wrap the existing `_collect_bgp_data` (line 1696), `_collect_network_metrics` (1914) with its sub-collectors (1992 to 2329), `_collect_observability` (1777), `_collect_cost_metrics` (2227) and `_collect_nta_metrics` (2163); each takes the normalized topology, fills the same model fields, and sets `ObservedState.state="observed"` only for resources it reached. `_collect_defender_assessments` (2420) moves to `DEFENDER_QUERY`; `_collect_nvas` (1555) to `NVA_QUERY`. `AzureDiscovery.run()` (line 2470) reads `CNA_DISCOVERY_BACKEND` (default `resource-graph`; `arm` keeps the current loop for one release). Remove `_validate_pe_dns` and the `socket` import; `AzurePrivateEndpoint.dns_resolves_to_private_ip` becomes `bool | None = None`.

- **Components affected.** `azure_discovery.py` (shrinks to orchestration), `module.yaml` permission list (F), `tests/unit/test_azure_discovery.py`, `VALIDATION.md`.
- **Tests.** Resource Graph fixtures (`tests/fixtures/resource_graph/*.json`, fictional subscriptions) drive `normalize_resource_graph` and `ResourceGraphDiscovery` with a fake client; `test_scopes.py` parses both scope shapes (`/subscriptions/00000000-0000-0000-0000-000000000001` and `/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/RG-Hub`), rejects anything else at startup, asserts the fake client is called with the subscription set only, and asserts `filter_to_scopes` keeps `rg-hub` rows and drops `rg-spoke` rows for the resource-group scope case-insensitively; one test proves paging consumes `skip_token` silently (no warning) and that a page stopped at the cap sets `truncated` and the warning; `test_attach_defender.py` and `test_attach_nvas.py` feed `DEFENDER_QUERY` and `NVA_QUERY` fixture rows and assert the NVA live rules and the Defender report section read them; one proves a Reader-only error from a live collector yields `state="unknown"` and no exception; ARM tests remain only for the live collectors.
- **Acceptance.** A Reader-only identity completes discovery of a subscription with zero `HttpResponseError` from list calls; wall time for a 500-resource subscription is recorded in `VALIDATION.md` and is seconds, not minutes; `git grep -n "gethostbyname" -- cna packages` is empty.
- **Priority** P2. **Dependencies** A, C, E. **Rollback** `CNA_DISCOVERY_BACKEND=arm` for one release; the flag is removed in the release after.

### 7.E Engine independence from `EngagementStore` and Postgres (change set E)

**Current behavior.** `AnalysisEngine.__init__(self, store: EngagementStore, options)` (`analysis_engine.py:152`); `run()` (line 1669 onward) reads `self.store.engagement_id`, loads topologies from the store and writes `FindingsReport` back; `main.py` imports `EngagementStore` (line 32) and `psycopg2` (line 20) in the same module as the rules.

**Required behavior.** `evaluate(topology) -> FindingsReport` has no I/O; the CLI and the API load and persist around it.

**Exact change.**

```python
# cna/ai_engine/analysis_engine.py (thin wrapper kept for the CLI)
class AnalysisEngine:
    def __init__(self, store: EngagementStore, options: AnalysisOptions | None = None): ...
    def run(self) -> FindingsReport:
        report = evaluate(self.store.load_azure_topology())
        if not self.opts.dry_run:
            self.store.write_findings_report(report)
        return report
```

`FindingsReport.engagement_id` becomes `str | None = None`; the CLI sets it. AWS rules stay in `AnalysisEngine` until change set K moves them.

- **Components affected.** `analysis_engine.py`, `cna/cli/analyze.py`, `main.py`, `tests/unit/test_analysis_engine.py`.
- **Tests.** `test_analysis_engine.py` fixtures call `evaluate(topology)` directly; `tests/unit/test_engine_has_no_io.py` asserts `cna_azure_network_engine` imports neither `cna.core.persistence` nor `psycopg2` (walk `sys.modules` after import).
- **Acceptance.** `git grep -n "EngagementStore\|psycopg2" -- packages/cna-azure-network-engine` is empty.
- **Priority** P1. **Dependencies** C. **Rollback** the wrapper class keeps the CLI contract; revert is a single commit.

### 7.F Least-privilege roles (change set F)

**Current behavior.** `sp-help-modal.tsx:93` says "minimum: Network Contributor"; line 176 titles Step 4 "Grant Network Contributor access"; 197 selects it; 209 to 211 advise it at management-group scope; 218 to 225 explain "Why Network Contributor and not Reader?" with a claim that gateway enumeration requires it (false: `virtual_network_gateways.list` is a read; only the BGP `begin_get_*` POST actions are not). `main.py:1146` recommends it in a finding. `module.yaml:27-35` lists eight `Microsoft.Network/*/read` actions. `.env.example:73` says "Reader at root Management Group + Management Group Reader".

**Required behavior.** One role table (section 13), repeated verbatim in all four places and in the appliance Terraform.

**Exact change.** New `docs/roles/cna-network-bgp-reader.json` (every action name checked on 2026-10-25 against the Microsoft Learn Azure permissions reference; re-check against the tenant with the Microsoft.Network provider operations list before `az role definition create`; `AssignableScopes` is set to the real scopes by whoever creates the role):

```json
{
  "Name": "CNA Network BGP Reader",
  "IsCustom": true,
  "Description": "Read-only BGP state for Cloud Network Assessment. POST actions that return data and change nothing.",
  "Actions": [
    "Microsoft.Network/virtualNetworkGateways/getBgpPeerStatus/action",
    "Microsoft.Network/virtualNetworkGateways/getLearnedRoutes/action",
    "Microsoft.Network/virtualNetworkGateways/getAdvertisedRoutes/action",
    "Microsoft.Network/virtualHubs/bgpConnections/learnedRoutes/action",
    "Microsoft.Network/virtualHubs/bgpConnections/advertisedRoutes/action",
    "Microsoft.Network/expressRouteCircuits/peerings/routeTables/read"
  ],
  "NotActions": [],
  "AssignableScopes": ["/subscriptions/00000000-0000-0000-0000-000000000001"]
}
```

- `sp-help-modal.tsx`: replace the four passages with the table; Step 4 becomes "Assign Reader (and the optional reader roles)"; the amber callout becomes "Why not Network Contributor?" stating the scan is read-only and the only non-read calls are the BGP actions in the custom role. After change set G this modal describes the managed identity instead of a service principal.
- `main.py:1146`: "Assign the Reader role at the subscription scope. For BGP state, also assign the custom role CNA Network BGP Reader."
- `module.yaml:27-35`: `Microsoft.Resources/subscriptions/resourceGroups/read`, `Microsoft.ResourceGraph/resources/read`, `Microsoft.Network/*/read`, `Microsoft.Insights/diagnosticSettings/read`, `Microsoft.Insights/Metrics/read`, `Microsoft.Security/assessments/read`, `Microsoft.CostManagement/query/action`, `Microsoft.OperationalInsights/workspaces/query/read`, plus the six custom-role actions, each checked against Microsoft Learn on 2026-10-25.
- `.env.example:73`: "Required RBAC: Reader on each assessed scope; optional Security Reader, Cost Management Reader, Log Analytics Reader, CNA Network BGP Reader (docs/roles/cna-network-bgp-reader.json)."

- **Components affected.** Web modal, API finding text, module manifest, env template, appliance Terraform (`azurerm_role_definition` plus assignments).
- **Tests.** `tests/unit/test_role_docs.py`: `git grep -n "Network Contributor" -- apps cna docs .env.example` is empty; the JSON parses and lists exactly the six actions.
- **Acceptance.** Discovery with exactly these roles produces zero permission warnings in the progress log (recorded in `VALIDATION.md` with R-008's acceptance run).
- **Priority** P1 (security; may land first). **Dependencies** none. **Rollback** text only; revert the commit.

### 7.G Appliance on Container Apps with UAMI; remove SP secrets (change set G)

**Current behavior.** `AzureDiscoveryOptions.client_id` and `client_secret` (`azure_discovery.py:97-98`); `_init_credentials` (line 239) builds `ClientSecretCredential` when both are set (line 247), else `DefaultAzureCredential()` (line 254). `TestConnectionRequest.sp_client_secret` (`main.py:1457`) feeds `/discovery/test-connection` (line 1460), which also imports `ClientSecretCredential`. `DiscoveryStartRequest.sp_client_secret` (line 1541). The web decrypts `spSecretEnc` in `discovery/actions.ts:34` and `cloud-credentials/actions.ts:235`, and encrypts at `cloud-credentials/actions.ts:41,92`. Prisma `CloudCredential.spSecretEnc` (`schema.prisma:217`). `cna/core/credential_crypto.py` is the Python twin of `lib/crypto.ts` and is also used for BYO AI keys (R-011).

**Required behavior.** No client secret exists anywhere; the appliance authenticates with its user-assigned managed identity; "test connection" validates the identity's access to the configured scopes.

**Exact change.**

```python
# cna_azure_network_engine/discovery/settings.py
FORBIDDEN_ENV = ("AZURE_CLIENT_SECRET", "AZURE_CLIENT_CERTIFICATE_PATH", "AZURE_USERNAME", "AZURE_PASSWORD",
                 "AZURE_FEDERATED_TOKEN_FILE", "AZURE_AUTHORITY_HOST")

@dataclass(frozen=True)
class ApplianceSettings:
    azure_client_id: str            # AZURE_CLIENT_ID, required: the user-assigned managed identity

    @classmethod
    def from_env(cls, env=os.environ) -> "ApplianceSettings":
        present = [k for k in FORBIDDEN_ENV if env.get(k)]
        if present:
            raise SystemExit(f"appliance edition: refusing to start, forbidden credential variables set: {present}")
        if not env.get("AZURE_CLIENT_ID"):
            raise SystemExit("appliance edition: AZURE_CLIENT_ID (user-assigned managed identity) is required")
        return cls(azure_client_id=env["AZURE_CLIENT_ID"])

# azure_discovery.py
@dataclass
class AzureDiscoveryOptions:
    tenant_id: str                  # AZURE_TENANT_ID: the tenant being assessed; it activates no credential path
    subscription_ids: list[str] = field(default_factory=list)
    resume: bool = False

def _init_credentials(self) -> None:
    from azure.identity import ManagedIdentityCredential   # the only azure.identity class the appliance imports
    self._credential = ManagedIdentityCredential(client_id=settings.azure_client_id)
```

`DefaultAzureCredential` is not used anywhere in the appliance: its chain honours `AZURE_CLIENT_SECRET`, certificate and username variables, the Azure CLI and developer tools, which is exactly the set of paths the owner decision rules out. `ManagedIdentityCredential(client_id=...)` can only ever obtain a token for the identity the Container App carries, and `ApplianceSettings.from_env()` runs before any client is built, so a deployment that sets `AZURE_CLIENT_SECRET` or `AZURE_TENANT_ID` together with any secret-shaped variable exits 1 instead of silently taking another path. The CLI's developer path (`cna discover azure` after `az login`) uses `AzureCliCredential` explicitly and only under `CNA_PROFILE=developer`, which the appliance image refuses (7.H).

`main.py`: delete `TestConnectionRequest.sp_client_id/sp_client_secret` and the `ClientSecretCredential` branch of `/discovery/test-connection`; replace with `POST /discovery/test-access {tenant_id, subscription_ids}` that lists each subscription with the process identity; delete `DiscoveryStartRequest.sp_client_id/sp_client_secret`. Web: remove the SP fields from `cloud-credentials/credential-form.tsx`, the `encrypt(spClientSecret)` calls and the `decrypt(cred.spSecretEnc)` reads; `buildStartPayload` sends `tenant_id` and `subscription_ids` only. Prisma migration `20261010000016_drop_sp_secret`: `ALTER TABLE "CloudCredential" DROP COLUMN "spSecretEnc"; ALTER TABLE "CloudCredential" DROP COLUMN "spClientId";` with a `down.sql` that re-adds both as nullable `TEXT`. `credential_crypto.py` and `lib/crypto.ts` stay for BYO AI keys only (R-011 unchanged). Terraform in the Azure appliance repo: `azurerm_user_assigned_identity`, `azurerm_role_assignment` `for_each` over `assessment_scope_ids` (Reader) plus the optional roles of 7.F; `AZURE_CLIENT_ID` env set to the identity's client id (section 12).

- **Components affected.** Discovery, API, web credential pages, Prisma, appliance Terraform, `sp-help-modal.tsx` (now a managed-identity help modal).
- **Tests.** `tests/unit/test_azure_discovery.py` credential tests assert `ManagedIdentityCredential` is constructed with `client_id` equal to `AZURE_CLIENT_ID` and that no other `azure.identity` class is imported by the discovery package; `tests/security/test_forbidden_env.py` calls `ApplianceSettings.from_env()` with each of `AZURE_CLIENT_SECRET`, `AZURE_CLIENT_CERTIFICATE_PATH`, `AZURE_USERNAME`, `AZURE_PASSWORD`, `AZURE_FEDERATED_TOKEN_FILE` set, and with `AZURE_TENANT_ID` set alongside a secret, and asserts `SystemExit` before any credential object exists (a patched `azure.identity` records zero constructions), plus `SystemExit` when `AZURE_CLIENT_ID` is absent; `tests/security/test_no_client_secret.py` asserts `git grep -n "ClientSecretCredential\|DefaultAzureCredential\|sp_client_secret\|spSecretEnc" -- apps cna packages` is empty; web `vitest` for the credential form.
- **Acceptance.** The grep is empty; `prisma migrate deploy` applies on a database that held the column; the appliance starts discovery with only `AZURE_CLIENT_ID` and `AZURE_TENANT_ID` set and refuses to start when any `FORBIDDEN_ENV` variable is present.
- **Priority** P1 (security; may land first). **Dependencies** none for the code; F for the role set. **Rollback** `down.sql`; the previous image by digest; users who need a non-identity path have none, by decision.

### 7.H API bearer auth and exception redaction (change set H)

**Current behavior.** `apps/cna-api/main.py` has no authentication import or dependency; `/intake` (1215), `/publish` (1290), `/discovery/test-connection` (1460), `/discovery/start` (1550), `/discovery/jobs/{job_id}` (1579) are open. `errorMessage=str(exc)` at 1704 and 1812; `topo.block_reason = str(e)` at `azure_discovery.py:441`; collector errors are joined into `block_reason` (line 479).

**Required behavior.** The internal routes (`/discovery/*`, `/intake`, `/publish`) require an Entra bearer token for the appliance's app registration **and** the `Discovery.Run` app role (or the declared scope); `/health`, `/api/health`, `/api/rules` and the read routes of section 8 keep their public contract; persisted error text is a status code and class name, full text at debug log only. There is no runtime switch that turns authentication off in an appliance deployment.

**Exact change.** New `apps/cna-api/auth.py` reading `CNA_ENTRA_TENANT_ID`, `CNA_ENTRA_AUDIENCE` (the `api://` identifier URI of the app registration), `CNA_ENTRA_JWKS_URL` (derived from the tenant) and `CNA_ENTRA_REQUIRED_ROLE` (default `Discovery.Run`):

```python
# apps/cna-api/auth.py
REQUIRED_ROLE = os.environ.get("CNA_ENTRA_REQUIRED_ROLE", "Discovery.Run")

async def require_bearer(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> dict:
    """Authenticate: signature (cached JWKS), iss, aud, exp -> 401 {error:{code:"unauthenticated"}} on failure.
    Authorize: REQUIRED_ROLE must be in claims.get("roles", []) (app role) or in claims.get("scp", "").split()
    (delegated scope) -> otherwise 403 {error:{code:"insufficient_role"}}. Returns the claims."""

# apps/cna-api/main.py: the dependency lives on one router, never on the FastAPI app
internal = APIRouter(dependencies=[Depends(require_bearer)])
internal.add_api_route("/discovery/start", start_discovery, methods=["POST"])
internal.add_api_route("/discovery/jobs/{job_id}", get_discovery_job, methods=["GET"])
internal.add_api_route("/discovery/test-access", test_access, methods=["POST"])
internal.add_api_route("/intake", intake, methods=["POST"])
internal.add_api_route("/publish", publish, methods=["POST"])
public = APIRouter()      # /health, /api/health, /api/rules, /api/assessments/current/*: no dependency
app.include_router(internal)
app.include_router(public)

# cna/api_errors.py
def redact_exception(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    return type(exc).__name__ + (f" (HTTP {status})" if status else "")
```

`require_bearer` is attached to the `internal` router only, so a public route can never inherit it by accident and a route that must be protected is registered on `internal` by name; `tests/unit/test_cna_api_auth.py` holds the list of protected paths and fails when a `/discovery/*`, `/intake` or `/publish` route is found outside that router. Test profile: `CNA_PROFILE=test` makes `require_bearer` accept a locally signed key (JWKS read from a file named by `CNA_ENTRA_JWKS_URL`) and is honoured only when `pytest` is the running process (`"pytest" in sys.modules`) or the build is not an appliance (`CNA_EDITION != "appliance"`); an appliance image that starts with `CNA_PROFILE` set to any value exits 1 with "appliance edition: CNA_PROFILE is not accepted". There is no `CNA_AUTH_DISABLED` or equivalent. The web tier obtains a token for `CNA_ENTRA_AUDIENCE` with its own user-assigned identity (`@azure/identity` `ManagedIdentityCredential`) and sends `Authorization: Bearer`; the appliance Terraform assigns the `Discovery.Run` app role to that identity's service principal (section 12). Replace the three `str(exc)` / `str(e)` sites with `redact_exception(...)`; the `_run` helper in `_discover_subscription` (lines 423 to 438) records `f"{attr}: {redact_exception(e)}"`.

- **Components affected.** `main.py`, `apps/cna-api/auth.py`, `cna/api_errors.py`, `azure_discovery.py`, web `lib/` API client, appliance Terraform (app registration with `identifier_uris`, app role, role assignment to the web identity; section 12).
- **Tests.** `tests/unit/test_cna_api_auth.py`: 401 without a token, 401 with the wrong audience, 403 `insufficient_role` with a valid token whose `roles` lacks `Discovery.Run` and whose `scp` is empty, 200 with the role in `roles`, 200 with the role in `scp`, every `/discovery/*`, `/intake`, `/publish` route registered on `internal`, `/api/health` and `/api/rules` 200 with no token; `tests/security/test_profile_refused.py`: the app factory exits 1 when `CNA_PROFILE=test` and `CNA_EDITION=appliance`; `tests/unit/test_api_errors.py`: redaction never includes the exception message.
- **Acceptance.** `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/discovery/jobs/x` prints `401`; the same request with a valid token lacking the role prints `403`; `GET /api/health` prints `200` with no token; no `errorMessage` row contains a hostname.
- **Priority** P1 (security; may land first). **Dependencies** none. **Rollback** the previous image digest; authentication configuration is never toggled at runtime.

### 7.I Lab boundary image target and boundary test (change set I)

**Current behavior.** Root `Dockerfile` builds the CLI image with graphviz, draw.io and xvfb; `apps/cna-api/Dockerfile` installs the API's dependencies inline (lines 17 to 39) including `boto3`, `psycopg2-binary`, `openai`, `anthropic`. There is no `tests/security/` directory.

**Required behavior.** One root `Dockerfile` builds the appliance image and a build-only `lab` target. The `lab` target installs the engine without `[azure]`, copies no `apps/`, runs no server, and its `CMD` is the boundary proof (exit 0 only when `azure` is not importable); it is built in CI and never pushed. The deployable lab build, its HTTP contract (`/api/health` with `edition: "lab"`, uploads, pane) and the checks on it belong solely to the AddOn, which builds `docker.io/hybridcloudworks/hcw-addon-network-assessment` from its own source on the published engine using this same Dockerfile pattern.

**Exact change.** Root `Dockerfile`, complete (digest-pinned base, uid 1001, pip removal and the stdlib healthcheck kept from `apps/cna-api/Dockerfile`):

```dockerfile
ARG EDITION=appliance
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS builder
ARG EDITION
WORKDIR /build
COPY packages/cna-azure-network-engine /build/engine
COPY pyproject.toml /build/cna-src/
COPY cna/ /build/cna-src/cna/
COPY apps/cna-api/ /build/cna-src/apps/cna-api/
RUN if [ "$EDITION" = "lab" ]; then \
      pip install --no-cache-dir --prefix=/install /build/engine; \
    elif [ "$EDITION" = "appliance" ]; then \
      pip install --no-cache-dir --prefix=/install -r /build/cna-src/apps/cna-api/requirements.txt \
   && pip install --no-cache-dir --prefix=/install "/build/engine[azure]" \
   && pip install --no-cache-dir --prefix=/install --no-deps /build/cna-src; \
    else echo "unknown EDITION=$EDITION" >&2; exit 1; fi

FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS final-lab
COPY --from=builder /install /usr/local
RUN python -m pip uninstall -y pip && groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --no-create-home --shell /usr/sbin/nologin cna
USER cna
ENV CNA_EDITION=lab
# The image's only job: exit 0 when azure is NOT importable, exit 1 when it is.
CMD ["python", "-c", "import importlib.util, sys; sys.exit(1 if importlib.util.find_spec('azure') else 0)"]

FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS final-appliance
# Body of apps/cna-api/Dockerfile lines 55 to 99 as today: drawio-fetch stage, apt upgrade, non-root uid 1001,
# COPY --from=builder /install, COPY cna/ and apps/cna-api/, pip removed, HEALTHCHECK on /health, uvicorn on 8080.
ENV CNA_EDITION=appliance

FROM final-${EDITION}
```

`apps/cna-api/requirements.txt` (new, exact pins; section 11) replaces the inline package list at `apps/cna-api/Dockerfile:17-39`. New `tests/security/test_lab_boundary.py` runs against a venv built with `pip install packages/cna-azure-network-engine` (no extra): `find_spec("azure") is None`; `importlib.metadata.distributions()` lists no name starting with `azure-`, `msal` or `boto3`; the engine's `edition.py` guard (shared with the AddOn) exits 1 with "lab edition" on stderr when `find_spec("azure")`, `msal` or `boto3` resolves or when any of `IDENTITY_ENDPOINT`, `MSI_ENDPOINT`, `AZURE_CLIENT_SECRET`, `AZURE_FEDERATED_TOKEN_FILE` is set. The lab HTTP checks (`/api/health` reporting `edition: "lab"`, `azureConnectivity: "disabled-by-design"`, no password inputs, image-level `import azure` on the shipped image) live in the AddOn's `tests/security/test_edition_boundary.py` and its image job, not here.

- **Components affected.** `Dockerfile`, `apps/cna-api/Dockerfile` (its body becomes the `final-appliance` stage; the file is deleted), `apps/cna-api/requirements.txt` (new), `200-build-images.yml` (the `lab` target is built with `push: false` and is never pushed), `tests/security/`.
- **Tests.** The venv tests above; `300-test-codebase.yml` gains a job `lab-image` that builds with `--build-arg EDITION=lab -t cna:lab`, runs `docker run --rm cna:lab` expecting exit 0 and `docker run --rm cna:lab python -c "import azure"` expecting exit 1.
- **Acceptance.** Both targets build from one Dockerfile; `docker run --rm cna:lab` exits 0; `docker run --rm cna:lab python -m pip` fails (pip removed); `cna:lab` appears in no registry and no manifest.
- **Priority** P2. **Dependencies** C. **Rollback** `EDITION` defaults to `appliance`, so existing builds are unchanged; the lab target is additive.

### 7.J Engine release workflow and image digests (change set J)

**Current behavior.** `310-release-version.yml` releases on tags `v*.*.*` (line 16) and pushes images; `200-build-images.yml` logs in with `secrets.DOCKERHUB_TOKEN` (lines 67 to 72) and wrote a build manifest with `sha-<7>` tags only (removed 2026-10-25).

**Required behavior.** A tag `engine-v*` builds, tests and publishes the wheel; the digests are recorded in the step summary and the release notes; publishing uses the Docker OIDC connection, not a long-lived token.

**Exact change.** New `.github/workflows/320-release-engine.yml`, `on: push: tags: ['engine-v*']`, top-level `permissions: contents: read`, `runs-on: ubuntu-26.04`, actions pinned to full commit SHAs re-verified with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` style lookups before merge (the Core's existing pins `actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` and `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` are reused). Three jobs with job-level permissions:

| Job | `permissions` | Steps |
|---|---|---|
| `build-test` | `contents: read` | `pip install uv && uv build packages/cna-azure-network-engine --out-dir dist`; install the wheel in a fresh venv, `python -c "import cna_azure_network_engine as e; print(e.RULES_VERSION)"`, run the package tests; upload `dist/` as an artifact |
| `publish-pypi` | `id-token: write`, `contents: read` | `if: vars.PYPI_PUBLISH_ENABLED == 'true'`; download the artifact; `uv publish --trusted-publishing always dist/*` (OIDC to PyPI through uv itself; no third-party publishing action and no token) |
| `release-upload` | `contents: write` | download the artifact; `gh release create "$GITHUB_REF_NAME" --verify-tag --notes-from-tag dist/*` with `GH_TOKEN: ${{ github.token }}`; this is the only job with write access to the repository |

In `200-build-images.yml`: replace the `login-action` step's `password: ${{ secrets.DOCKERHUB_TOKEN }}` with the website's OIDC form (`env: DOCKERHUB_OIDC_CONNECTIONID: ${{ vars.DOCKERHUB_CONNECTION }}`, `DOCKERHUB_OIDC_EXPIREIN: '900'`, `with: registry: docker.io, username: hybridcloudworks`; gate on `vars.DOCKERHUB_ENABLED == 'true'`); record the digest of each of `cli, api, worker, web, migrator` in the step summary of `tag-images` and in the `310` release notes (the `lab` target is built with `push: false` and has no entry); nothing is written to the repository; keep the Scout gate by digest.

- **Components affected.** Workflows, `docs/release/`.
- **Tests.** `actionlint`; the digest shape is checked by `scripts/ci/verify_signed_digest.sh` and `scripts/ci/release_digests.sh`.
- **Acceptance.** `pip download cna-azure-network-engine --no-deps -d ./wheel` succeeds once publishing is enabled; the step summary carries a digest for every image.
- **Priority** P3. **Dependencies** C, I. **Rollback** the workflow is additive; the old login step is one commit away.

### 7.K AWS gating behind an extra (change set K)

**Current behavior.** `boto3` is a base dependency (`pyproject.toml:13`) and is installed in the API image (`apps/cna-api/Dockerfile:30`); AWS classes (A), `_check_aws_*` rules (`analysis_engine.py:198-638`), `cna/modules/network/discovery/{aws_discovery,aws_network}.py`, `cna/modules/security/discovery/aws_security.py`, `cna/delivery_portal/s3_deployer.py`, `cna/ai_engine/mcp_client/aws_mcp_client.py`, the Bedrock branches in `chat_agent.py` and `apps/cna-web/lib/ai-engine.ts`, `cna/diagram_engine/data/aws_shapes.json`, `cna/modules/network/diagrams/{vpc_topology,tgw_topology,account_hierarchy}.py`, Prisma migration `20260828000014_aws_credentials`, `CRITICAL_TRIGGERS_AWS` (`escalation_engine.py:9`), `tests/unit/test_aws_discovery.py`, `test_aws_security.py`.

**Required behavior.** `pip install cna` installs no `boto3`; `pip install "cna[aws]"` enables every AWS path; shared files separate the two clouds.

**Exact change.** `pyproject.toml`: move `boto3` to `optional-dependencies.aws`; new `cna/aws/__init__.py` raising `ImportError("install cna[aws]")` when `boto3` is absent; move the listed modules under `cna/aws/` with re-export shims at the old paths for one release; `module.yaml` splits `required_permissions.aws` into `cna/modules/network/module.aws.yaml`; `.env.example` and `README.md` gain an "AWS (optional)" section; `/discovery/test-connection-aws` (`main.py:1495`) and `_run_aws_discovery` (1710) return `501 aws_not_installed` when the extra is missing.

- **Components affected.** Packaging, discovery, rules, diagrams, delivery portal, AI engine, API, docs.
- **Tests.** `tests/packaging/test_azure_only_install.py`: a clean venv with `pip install .` has no `boto3`; AWS tests are marked `@pytest.mark.aws` and skipped without the extra.
- **Acceptance.** `pip install . && python -c "import boto3"` fails; `pip install ".[aws]"` passes the AWS tests.
- **Priority** P3. **Dependencies** A. **Rollback** shims keep old imports; moving `boto3` back to base is one line.

## 8 Required API changes

The appliance build serves two API surfaces: the existing internal `cna-api` (now bearer-authenticated) and a small public, anonymous, read-only surface in the shape the AddOn standard fixes (`CONTRACT-DECISIONS` items 10 and 16: flat envelope, `id` and `version` at the top level).

| Method and path | Build | Auth | Behaviour |
|---|---|---|---|
| `GET /api/health` | appliance (the AddOn serves the `lab` form of the same envelope from its own image) | none | 200 `{ ok, id: "network-assessment", version, edition: "appliance", capabilities[], asOf, siteOrigins[], turnstile: { required: false, siteKey: null }, azureConnectivity: "managed-identity", rules: { version, count, liveOnly }, model: { version }, scopes: <count>, lastRefreshAt }`; `ok:false` with 503 when the rule registry failed to load. Never 5xx on store state |
| `GET /api/assessments/current` | appliance | none | 200 `{ assessment: { summary, findings, resources, unknowns, warnings }, refreshedAt, nextRefreshAt }`; 503 `refreshing` before the first refresh completes |
| `GET /api/assessments/current/report.md` | appliance | none | `text/markdown`, attachment |
| `GET /api/assessments/current/report.json` | appliance | none | report plus `rules` and `model` versions |
| `GET /api/assessments/current/bundle.zip` | appliance | none | STORE zip: `README.md`, `report.md`, `findings.json`, `topology.json`, `summary.json`, `rules.json`, `NOT-FOR-PRODUCTION.md` |
| `GET /api/rules` | appliance (the AddOn serves its own) | none | registry serialised: `[{ id, title, severity, category, version, appliesTo, evidence, learnUrl, frameworks }]` |
| `POST /api/assessments` | appliance | none | **405** from a deliberate handler registered for `POST` on the `public` router: header `Allow: GET`, body `{ error: { code: "edition_readonly", message: "This edition assesses its configured scopes and accepts no uploads." } }`. FastAPI's default 405 carries neither the envelope nor a reliable `Allow`, so the handler is explicit; `tests/unit/test_public_api.py` asserts status, `Allow` and `error.code`, and `tests/security/test_appliance_boundary.py` asserts no route under `/api/assessments` accepts a body |
| `POST /api/refresh` | appliance | bearer + `Discovery.Run` | 202; at most once per 60 s; otherwise 429 with `Retry-After` |
| `POST /discovery/start`, `GET /discovery/jobs/{id}`, `POST /publish`, `POST /intake`, `POST /discovery/test-access` | appliance (internal `cna-api`, `internal` router) | **bearer + `Discovery.Run`** (7.H) | Unchanged shapes except the removed `sp_*` fields; 401 `unauthenticated` without a valid token; 403 `insufficient_role` with a valid token lacking the role |
| `GET /health` | internal `cna-api` | none | Kept as is (`main.py:1205`) for the container healthcheck |

Headers on every response: `X-Addon-Id: network-assessment`, `X-Addon-Version`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on API routes; CSP with `frame-ancestors` from `NA_FRAME_ANCESTORS` (default `'none'`). `X-Frame-Options: DENY` is sent only when `NA_FRAME_ANCESTORS` is exactly `'none'`; for any other value the header is omitted and CSP `frame-ancestors` alone governs, because `X-Frame-Options` cannot express an origin list and a `DENY` beside a permissive `frame-ancestors` would block the site's own pane (the same rule as `CONTRACT-DECISIONS` item 11 and the AddOn standard section 11). Error envelope everywhere: `{ error: { code, message, details? } }`, with `message` free of hostnames, paths and stack text.

## 9 Required data contract changes

| Contract | At `5d3b914` | Required |
|---|---|---|
| Topology model version | `TOPOLOGY_SCHEMA_VERSION = "1.3.0"` shared by AWS and Azure (`topology_schema.py:32`) | `TOPOLOGY_MODEL_VERSION = "1.3.0"` in the engine; the AddOn's interim `lab-1.0.0` is declared equivalent in its `PROVENANCE.md` and is replaced by the engine's constant when the wheel is adopted. Carried in every `report.json` and in `/api/health model.version` |
| `ObservedState` | `fact: str`, `evidence_ref: str` (`findings_schema.py:30-32`) | `state: Literal["observed", "unknown", "not-applicable"] = "observed"`, `fact`, `evidence_ref`. `unknown` when the input a rule needs is absent (no flow-log rows, Reader-only identity for a live collector); `not-applicable` when the rule's precondition is false. The string coercion validator (lines 65 to 71) stays |
| `Finding` | fields at lines 53 to 91, including MCP fields and `est_monthly_cost_usd` | Keep `id, rule_id, severity, platform, region, category, title, description, resource_id, resource_type, account_id, observed_state, affected_resources, framework_mappings, traffic_direction, created_at, version`; add `rule_version: int`, `remediation: str | None`, `learn_url: str | None`; drop `recommendation_source`, `human_reviewed`, `human_notes`, `est_monthly_cost_usd` and `FindingRecommendation.source` from the engine model (the monorepo may keep a subclass with them for the web tier) |
| `FindingsReport` | `engagement_id: str` required (line 95) | `engagement_id: str | None = None`; add `rules_version: str`, `model_version: str`, `unknowns: list[Unknown]` where `Unknown = { rule_id, reason }` |
| Rule registry | none; Engine B has no ids | `RULES_VERSION` (calendar string, hash-pinned in a test); every rule has `id, title, severity, category, version, learn_url, frameworks, applies_to, evidence`; live-only rules are registered and surface in `unknowns[]` |
| Resource Graph row | not consumed | `{ id, name, type, location, resourceGroup, subscriptionId, tags, zones, sku, kind, properties }`; `type` lower-cased; `resourceGroup` and `subscriptionId` derived from `id` when absent; the `az graph query` envelope `{ count, data, skip_token, total_records }` is accepted by the normalizer's caller. A `skip_token` is followed by the Core's discovery until it is exhausted and normal paging records nothing; a warning is recorded only when a token remains unconsumed (paging stopped at the row cap or a page failed) or `total_records` exceeds the rows received (truncated response). An uploaded envelope that still carries a `skip_token` is by definition unconsumed, which is why the lab build warns on it |
| Prisma `CloudCredential` | `spClientId`, `spSecretEnc` (`schema.prisma:216-217`) | Dropped by migration `20261010000016_drop_sp_secret` (7.G) |
| Build record | `{ sha_tag, commit, built_at, run_id, images{} }` in a manifest file | digest table in the `tag-images` step summary, one row per component (no `lab` entry: that target is never pushed); no manifest file (2026-10-25) |

## 10 Configuration changes

| Variable | Build | Default | Purpose | Source at `5d3b914` |
|---|---|---|---|---|
| `CNA_EDITION` | appliance; `lab` only in the build-only boundary target | `appliance` | Set by the Dockerfile `ARG EDITION`; the engine's guard refuses `lab` with any Azure SDK present and refuses `appliance` without `AZURE_CLIENT_ID` | new |
| `CNA_DISCOVERY_BACKEND` | appliance | `resource-graph` | `arm` keeps the old loop for one release (7.D) | new |
| `CNA_SCOPES` | appliance | required | Space-separated scope ids of the form `/subscriptions/<sub>` or `/subscriptions/<sub>/resourceGroups/<rg>`; parsed at startup (7.D `parse_scopes`, anything else exits 1); the subscription set goes to Resource Graph and rows outside a resource-group scope are dropped case-insensitively before normalization | new |
| `CNA_REFRESH_SECONDS` | appliance | `900` | Timer-driven refresh interval | new |
| `CNA_INCLUDE_MANAGEMENT_GROUPS` | appliance | `0` | Enables the Management Group Reader path | new |
| `AZURE_CLIENT_ID` | appliance | required | Client id of the user-assigned managed identity; `ManagedIdentityCredential(client_id=...)` is the only credential; startup exits 1 when absent (7.G) | `.env.example:65` |
| `AZURE_TENANT_ID` | appliance | required | The tenant being assessed (`AzureDiscoveryOptions.tenant_id`); activates no credential path | `.env.example:64` |
| `AZURE_CLIENT_SECRET`, `AZURE_CLIENT_CERTIFICATE_PATH`, `AZURE_USERNAME`, `AZURE_PASSWORD`, `AZURE_FEDERATED_TOKEN_FILE`, `AZURE_AUTHORITY_HOST` | none | forbidden | `FORBIDDEN_ENV` (7.G): the appliance refuses to start when any is set; the lab guard refuses `AZURE_CLIENT_SECRET` and `AZURE_FEDERATED_TOKEN_FILE` too. `AZURE_CLIENT_SECRET` was `.env.example:66` | removed |
| `CNA_ENTRA_TENANT_ID`, `CNA_ENTRA_AUDIENCE`, `CNA_ENTRA_JWKS_URL`, `CNA_ENTRA_REQUIRED_ROLE` | appliance | required; role default `Discovery.Run` | Bearer validation and app-role authorization for the `internal` router (7.H) | new |
| `CNA_PROFILE` | never in an appliance deployment | unset | `test` is honoured only under pytest or a non-appliance build (local JWKS file); `developer` selects the CLI's `AzureCliCredential` path outside the appliance; the appliance image exits 1 when the variable is set at all (7.G, 7.H) | new |
| `NA_FRAME_ANCESTORS` | both | `'none'` | CSP `frame-ancestors` on the public surface | new |
| `NA_SITE_ORIGINS` | both | empty | Origins the pane may post to; mirrored in `/api/health siteOrigins` | new |
| `NA_TRUST_PROXY` | both | `0` | Take the first `X-Forwarded-For` for rate limiting | new |
| `NA_RATE_LIMIT_POSTS`, `NA_RATE_LIMIT_WINDOW_MINUTES` | both | `10`, `10` | Token bucket on `POST /api/refresh` (appliance) and uploads (lab) | new |
| `DATABASE_URL`, `CNA_API_INTERNAL_URL`, `AZURE_STORAGE_ACCOUNT_NAME` | appliance (cna-api, cna-web) | as today | Unchanged | `.env.example:156,82` |
| `CREDENTIAL_ENCRYPTION_KEY` | appliance | as today | BYO AI keys only after 7.G | `.env.example:28` |
| `PORT` | both | `8080` | Already the API's port (`apps/cna-api/Dockerfile:99`) | unchanged |

`.env.example` gains the new rows with empty values and loses `AZURE_CLIENT_SECRET`; it keeps no secret values. The AddOn's own `NA_*` variables (Turnstile, TTL, upload caps) are not Core configuration.

## 11 Dependency changes

| Package | At `5d3b914` | Required |
|---|---|---|
| `pydantic` | base `>=2.13.4` | Engine base, pinned `>=2.13,<3` |
| `azure-identity`, `azure-mgmt-network`, `azure-mgmt-resource`, `azure-mgmt-subscription` | base | Engine `[azure]` extra; `azure-mgmt-resource` and `-subscription` only if the containers query is not enough `[VERIFY]` |
| `azure-mgmt-resourcegraph` | absent | Engine `[azure]` extra (new) |
| `azure-mgmt-monitor<7`, `azure-monitor-query<3`, `azure-mgmt-costmanagement<5`, `azure-mgmt-loganalytics<15`, `azure-mgmt-security<8` | `enrichment` extra (`pyproject.toml:71-82`) | Engine `[azure]` extra with the same upper bounds and the same justification comment |
| `azure-mgmt-managementgroups<2`, `azure-mgmt-compute<39`, `azure-mgmt-privatedns<3` | `enrichment` | Dropped from discovery (Resource Graph covers management groups, VMs, NICs and private DNS zones); kept in the monorepo `enrichment` extra only if another module uses them |
| `boto3` | base (`pyproject.toml:13`) and API image | Monorepo `aws` extra only (7.K); never in the engine |
| `azure-ai-projects<2`, `azure-ai-agents<2`, `openai`, `anthropic`, `mcp` | base / `enrichment` | Monorepo `ai` extra; never in the engine |
| `psycopg2-binary`, `fastapi`, `uvicorn` | API image inline | `apps/cna-api/requirements.txt` with exact pins, installed by the root Dockerfile for `EDITION=appliance`; the engine's public API server pins `fastapi` and `uvicorn` exact (`[VERIFY]` versions at lock time) |
| `weasyprint`, `matplotlib`, `diagrams`, `n2g`, `python-docx`, `python-pptx`, `jinja2`, `cairosvg` | base / `enrichment` | Monorepo `render` extra; never in the engine or the lab image |
| `cryptography` | base | Monorepo base (BYO AI keys); not in the engine |
| `requires-python` | `>=3.11` (`pyproject.toml:9`) | `>=3.14` for the engine and the monorepo (the images already run 3.14; CI drops the 3.13 matrix entry at `300-test-codebase.yml:137`) |
| `ty` | dev, not gating (T-402, T-410) | Unchanged; A and E reduce the finding count |
| `pip-audit` | absent | dev extra; run in CI against the engine's lock; a dependency with a known CVE is flagged before use |

## 12 Infrastructure changes

Terraform is not in this repository (T-504); this section records the resources a deployment of the appliance needs, and whoever deploys it writes the files.

Pattern: `/home/user/HCW-AzMigrateOrchestrator_App/infrastructure/terraform/appliance-azure/main.tf` (read only): `azurerm_resource_group`, `azurerm_user_assigned_identity`, `azurerm_role_assignment.reader` with `for_each = toset(var.assessment_scope_ids)`, `azurerm_log_analytics_workspace`, `azurerm_container_app_environment`, `azurerm_container_app` with `identity { type = "UserAssigned" }`, `ingress { external_enabled = true }`, `env { name = "AZURE_CLIENT_ID", value = azurerm_user_assigned_identity.app.client_id }`, and an `azuread_application` for the API audience.

| Resource | Setting |
|---|---|
| `azurerm_container_app.api` | `revision_mode = "Single"`; `template { min_replicas = 1, max_replicas = 1 }` (`CONTRACT-DECISIONS` item 21: scale-to-zero loses the in-memory snapshot; the zero-replica trade is documented as an owner option, not the default); `cpu = 0.5`, `memory = "1Gi"`; `target_port = 8080`; image `docker.io/hybridcloudworks/img-ne-appliance-app@sha256:...` taken from the `api` digest in the `200` step summary or the `310` release notes, never a floating tag |
| `env` | `CNA_EDITION=appliance`, `CNA_SCOPES`, `CNA_REFRESH_SECONDS=900`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `CNA_ENTRA_*`, `NA_FRAME_ANCESTORS`, `NA_SITE_ORIGINS`, `NA_TRUST_PROXY=1` |
| `azurerm_role_assignment` | `Reader` `for_each` over `assessment_scope_ids`; optional `Security Reader`, `Cost Management Reader`, `Log Analytics Reader` (on `var.log_analytics_workspace_ids`) behind `var.enable_live_rules` |
| `azurerm_role_definition.bgp_reader` | From `docs/roles/cna-network-bgp-reader.json` with `assignable_scopes = var.assessment_scope_ids`; assigned with the live rules flag |
| `azuread_application.api` | `identifier_uris` set to the `api://` form of its client id after creation; app role `Discovery.Run` (`allowed_member_types = ["Application"]`) |
| `azuread_app_role_assignment.web` | Assigns `Discovery.Run` on the API's service principal to the web tier's user-assigned identity (`principal_object_id = azurerm_user_assigned_identity.web.principal_id`); without it the web tier's token is valid but gets 403 `insufficient_role` (7.H) |
| `azurerm_log_analytics_workspace` | 30-day retention, as the pattern |
| `azurerm_consumption_budget_resource_group` | Monthly budget with one alert `[VERIFY amount]` |
| Images | Docker Hub `docker.io/hybridcloudworks/img-ne-appliance-app:*` by digest; published by `200-build-images.yml` through the Docker OIDC connection (`vars.DOCKERHUB_CONNECTION`, `vars.DOCKERHUB_ENABLED`), the pattern the website's `publish-lab-image.yml` uses; the Core already publishes to Docker Hub, so this is a login-step change, not a registry move |

Clients set `assessment_scope_ids`, `tenant_id` and `image_digest` in `terraform.tfvars`, and run `terraform plan` then `terraform apply`; `terraform apply` is a human-reviewed step and is never run from an automated session. The lab build is not deployed on Container Apps: it runs on the Hostinger lab host from the AddOn's image (AddOn ADR-0003).

## 13 Security changes

| Change | Set | Before | After |
|---|---|---|---|
| Internal API authentication and authorization | H | None (`main.py`) | Entra bearer, JWKS-validated, audience-bound, `Discovery.Run` app role or scope required (403 `insufficient_role` otherwise); attached to the `internal` router only; `/health`, `/api/health`, `/api/rules` and the read routes stay public; no runtime off switch |
| User-supplied secret path | G | `ClientSecretCredential` (`azure_discovery.py:247`), `sp_client_secret` (`main.py:1457,1541`), `spSecretEnc` (`schema.prisma:217`) | Removed; `ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)` is the only credential class imported (`DefaultAzureCredential` nowhere in the appliance); `FORBIDDEN_ENV` variables refuse startup; Prisma column dropped |
| Role guidance | F | Network Contributor in four places | Table below, repeated verbatim everywhere |
| Private-endpoint DNS evidence | D | Scanner-host `gethostbyname` (`azure_discovery.py:1101`) | Removed; field `None`, state `unknown` |
| Persisted error text | H | `str(exc)` (`main.py:1704,1812`; `azure_discovery.py:441`) | Class name and status only |
| Lab boundary | I | None | No Azure SDK installed; startup refusal on identity env; image-level `import azure` must fail; `edition: lab` in health |
| Scope allow-list | D, G | None (any subscription the SP could read) | `CNA_SCOPES` enforced before any query |
| Supply chain | J | Docker Hub token secret | OIDC connection; digests in the step summary and the release notes; Scout and `pip-audit` gates |
| AWS surface | K | Always installed | Optional extra |
| Rate limiting on the public surface | 8 | n/a | Token bucket per client, `X-Forwarded-For` only with `NA_TRUST_PROXY=1`, never `CF-Connecting-IP` |

Roles table (the single source for 7.F, section 12 and the appliance docs):

| Role | Built-in or custom | Grants | Required for |
|---|---|---|---|
| Reader | built-in | All `*/read`, Resource Graph | Every export rule and Resource Graph discovery |
| Security Reader | built-in | `Microsoft.Security/*/read` | Defender assessments |
| Cost Management Reader | built-in | `Microsoft.CostManagement/*/read`, `query/action` | `AZ-COST-002/003/005` |
| Log Analytics Reader | built-in | `workspaces/query/read`, shared keys excluded | Traffic Analytics (`AZ-NET-014` live form) |
| CNA Network BGP Reader | custom (`docs/roles/cna-network-bgp-reader.json`) | six actions, all checked against Microsoft Learn on 2026-10-25 | BGP peer status, learned and advertised routes |
| Management Group Reader | built-in | `Microsoft.Management/managementGroups/read` | Management-group tree (optional) |

Unchanged by this document and still open: R-011 (BYO AI key path and egress review) and the deploy service principal's least-privilege gaps recorded in `CNA-0.90-updates.md` section 5.

## 14 Testing requirements

| Set | Tests (path in the Core) | Gate |
|---|---|---|
| A | `tests/unit/test_topology_models.py` (both import paths); `tests/unit/test_topology_shim_warns.py` | unit |
| B | `tests/unit/rules/test_azure_net_020_033.py`, `test_azure_bcdr_006_007.py`, `tests/unit/test_registry.py` (ids unique, hedge-free text, `RULES_VERSION` hash); `tests/unit/test_cna_api_worker_decision.py` updated; a test asserting `main.py` defines no `_check_*` | unit |
| C | `tests/packaging/test_engine_wheel.py` (clean venv, no `azure-*`, `boto3`, `psycopg2`) | packaging job |
| D | `tests/unit/discovery/test_resource_graph.py` (paging, fixtures, Reader-only error to `unknown`); live collector tests kept; `VALIDATION.md` timing entry | unit + live acceptance (R-008) |
| E | `tests/unit/test_analysis_engine.py` on `evaluate()`; `tests/unit/test_engine_has_no_io.py` | unit |
| F | `tests/unit/test_role_docs.py` (no "Network Contributor"; JSON lists six actions) | unit |
| G | `tests/unit/test_azure_discovery.py` credential tests (`ManagedIdentityCredential` only); `tests/security/test_forbidden_env.py` (each forbidden variable, and `AZURE_TENANT_ID` beside a secret, refuses startup before any credential is built; missing `AZURE_CLIENT_ID` refuses); `tests/security/test_no_client_secret.py` (grep includes `DefaultAzureCredential`); web `vitest` credential form; `prisma migrate` in the `migrator` image build | unit + image |
| H | `tests/unit/test_cna_api_auth.py` (401 no token, 401 wrong audience, 403 `insufficient_role`, 200 role in `roles`, 200 role in `scp`, protected routes all on the `internal` router, public routes 200 without a token); `tests/security/test_profile_refused.py` (`CNA_PROFILE` set in an appliance build exits 1); `tests/unit/test_api_errors.py` | unit |
| 8 (public API) | `tests/unit/test_public_api.py` (`POST /api/assessments` is 405 with `Allow: GET` and `error.code == "edition_readonly"`; `X-Frame-Options: DENY` present only when `NA_FRAME_ANCESTORS` is exactly `'none'`); `tests/security/test_appliance_boundary.py` (no route under `/api/assessments` accepts a body) | unit |
| I | `tests/security/test_lab_boundary.py` against the engine venv without `[azure]`; CI `lab-image` job: `docker run --rm cna:lab` exits 0 and `docker run --rm cna:lab python -c "import azure"` exits 1; the lab HTTP checks are the AddOn's | unit + image job |
| J | `actionlint`; `tests/security/test_standalone_boundary.py` | CI |
| K | `tests/packaging/test_azure_only_install.py`; `@pytest.mark.aws` skips | packaging job |
| Ported to the AddOn and kept green upstream | `TestAzureNetFindingRules`, `TestAzurePeeringGatewayTransit`, `TestObservedStateEnforcer` in `test_analysis_engine.py`; `test_bcdr_signals.py`; `test_topology_classifier.py`; `test_finops_signals.py` (001 and 004 cases); `test_findings_schema.py` | unit |

Coverage: the existing `fail_under = 80` gate stays (T-408 keeps both discovery orchestrators measured); the engine package's own `pyproject.toml` sets `fail_under = 85`. `npm run lint` in `apps/cna-web` stays broken until T-419 is done; it is not made a gate here.

## 15 Migration sequence

Order: **A -> C -> (B, E) -> D -> F -> G -> H -> I -> J -> K.** F, G and H are independent security fixes and may land first, in any order, before A.

| Step | Lands | Release | Notes |
|---|---|---|---|
| 0 | F, G, H (any order) | `v0.9.0` | Security fixes; no engine change; the Prisma migration ships with the `migrator` image |
| 1 | A | `v0.9.1` | Shim in place; nothing else changes |
| 2 | C, E | `engine-v0.1.0` (wheel) + `v0.10.0` | First wheel; the AddOn adopts it and deletes its port. **Status 2026-10-24:** `engine-v0.1.0` is published (2026-10-12); the AddOn has not adopted it yet; no `v0.10.0` tag exists (tags: `v0.1.0`, `v0.8.0`, `engine-v0.1.0`) |
| 3 | B | `engine-v0.2.0` + `v0.10.1` | `RULES_VERSION` bump; web findings gain ids |
| 4 | D | `v0.11.0` | `CNA_DISCOVERY_BACKEND` defaults to `resource-graph`; `arm` kept one release |
| 5 | I | `v0.11.1` | Build-only lab boundary target; boundary test in CI; the AddOn ships the deployable lab build |
| 6 | J | `v0.11.2` | OIDC login; digests in the step summary and the release notes |
| 7 | K | `v0.12.0` | AWS extra; remove the A shims and the `arm` backend in the same release |

One PR per change set, ready for review, following the Core's PR template; `CHANGELOG.md` `[Unreleased]` (line 10) gains one entry per set.

## 16 Compatibility considerations

- **Import shims (A, K).** `cna.core.topology_schema` and the moved AWS module paths keep working for one release with a `DeprecationWarning`; CI runs with `-W error::DeprecationWarning` for the Core's own code only after the shims are deleted.
- **Discovery backend flag (D).** `CNA_DISCOVERY_BACKEND=arm|resource-graph`; default `resource-graph`; the `arm` value and the old loop are deleted in step 7.
- **Consumers of the images.** They pull by digest. From K the published images carry the `[aws]` extra (`TODO.md` T-729).
- **Web tier.** The findings page reads the rule id from the title prefix (`_finding_model_to_dict`, `main.py:1176`); B keeps that convention until a `ruleId` column is added in a later migration.
- **AddOn.** `TOPOLOGY_MODEL_VERSION`, `RULES_VERSION`, rule ids and severities in B are the contract the AddOn's interim port already uses; a Core change to any of them is a `[VERIFY]` item in the AddOn's `core-update` PR.
- **Python floor.** `>=3.14` matches the images; a 3.13 developer environment runs `uv python install 3.14`.
- **Entra bearer (H).** The web tier must send a token carrying `Discovery.Run` before the API enforces it: the web image, the app role assignment (section 12) and the API image ship in the same release, web first. There is no runtime toggle; a mismatch is rolled back by deploying the previous API image digest.

## 17 Rollback considerations

| Set | Rollback |
|---|---|
| A | Shim keeps old imports; revert the import rewrite commit |
| B | `git revert` of the `main.py` deletion; the rules module stays and is unused |
| C | Delete `packages/` and the dependency line; re-exports become the real modules again |
| D | `CNA_DISCOVERY_BACKEND=arm` (one release); then image digest rollback |
| E | The wrapper class keeps the CLI contract; revert is one commit |
| F | Text only; revert |
| G | `down.sql` restores the columns; previous `migrator` and `api` images by digest; no path back to SP secrets by decision |
| H | Previous API image digest; authentication configuration is never toggled at runtime |
| I | `EDITION` defaults to `appliance`; the lab target is additive |
| J | The old login step is one commit away; `images{}` is unchanged |
| K | Shims; `boto3` back to base is one line |
| Appliance | Previous image digest in `terraform.tfvars`, `terraform plan` then `terraform apply` (human-reviewed); `terraform destroy` of the resource group as the last resort |

## 18 Prioritized implementation backlog

| Priority | Item | Set | Maps to |
|---|---|---|---|
| P1 | Entra bearer on `cna-api`; redaction helper | H | new; closes the "no authentication" security observation |
| P1 | Remove `ClientSecretCredential`, `sp_client_secret`, `spSecretEnc`; UAMI only | G | R-011 (crypto path narrowed to AI keys; the review itself unchanged) |
| P1 | Least-privilege role table and custom role JSON | F | R-008 (acceptance re-run with the new roles); `CNA-0.90-updates.md` section 5 |
| P1 | Split `topology_schema.py` | A | T-410 (`ty` findings reduced) |
| P1 | Extract `cna-azure-network-engine` | C | T-413, T-414 (pins and extras absorbed into the engine's `[azure]` extra) |
| P1 | Pure `evaluate()`; engine without `EngagementStore` | E | T-412 (store read-side now outside the engine) |
| P2 | Unify Engine A and B; typed `AZ-NET-020..033`, `AZ-BCDR-006/007` | B | T-417 (ids make the four generated reports consistent) |
| P2 | Resource Graph discovery; remove scanner-host DNS | D | T-403, T-408 (fixtures replace SDK mocks; coverage stays measured); R-008 (live acceptance on the new backend) |
| P2 | Build-only lab boundary target and `tests/security/test_lab_boundary.py` | I | new |
| P3 | `320-release-engine.yml`; OIDC login; digests | J | T-503 (withdrawn 2026-10-25); T-504 to T-508 done, unaffected |
| P3 | AWS behind an extra | K | T-404 (boto3 and azure-mgmt consistency gaps close by separation); T-418 (diagrams stay Azure-only) |
| P3 | Remove the 52 MB vendored agent configuration from the product tree or move it to a separate repository | hygiene | T-411 (detect-secrets triage shrinks) |
| Unaffected | R-009 (Wiki access), R-012 (project board token), T-401, T-405 to T-407, T-409, T-415, T-416, T-419, T-501, T-502, T-505 | | Owner items; listed so the mapping is complete |

## 19 Acceptance criteria

1. `pip install ./packages/cna-azure-network-engine` in a clean venv installs `pydantic` only; `python -c "import cna_azure_network_engine as e, sys; print(e.RULES_VERSION); assert 'azure' not in sys.modules"` prints the version.
2. `pip install "./packages/cna-azure-network-engine[azure]"` adds discovery; `python -c "from cna_azure_network_engine.discovery import ResourceGraphDiscovery"` succeeds.
3. `git grep -c "def _check_" -- apps/cna-api/main.py` prints nothing; `git grep -n "Network Contributor" -- apps cna docs .env.example` prints nothing; `git grep -n "ClientSecretCredential\|DefaultAzureCredential\|sp_client_secret\|spSecretEnc\|gethostbyname" -- apps cna packages` prints nothing.
4. `docker build --build-arg EDITION=lab -t cna:lab .` succeeds, `docker run --rm cna:lab` exits 0 and `docker run --rm cna:lab python -c "import azure"` exits 1; the image is never pushed and has no digest row; `docker build --build-arg EDITION=appliance -t cna:appliance .` succeeds.
5. `GET /api/health` on the appliance returns `edition: "appliance"`, `azureConnectivity: "managed-identity"`, `id: "network-assessment"` and `version` at the top level, with no token. The `lab` form of the envelope is the AddOn's acceptance, on its own image.
6. `POST /api/assessments` on the appliance returns 405 with header `Allow: GET` and `error.code == "edition_readonly"`.
7. `GET /discovery/jobs/anything` on `cna-api` without a bearer token returns 401; with a valid token lacking `Discovery.Run` it returns 403 `insufficient_role`; the appliance exits 1 at startup when `CNA_PROFILE` or any `FORBIDDEN_ENV` variable is set.
8. A Reader-only identity completes Resource Graph discovery of a subscription with zero `HttpResponseError` from list calls; live-only rules report `state: "unknown"` with a reason; the timing is recorded in `VALIDATION.md`.
9. Every finding carries `rule_id`, `rule_version`, `observed_state.state`; every rule title and description passes `ObservedStateEnforcer`; `RULES_VERSION` changes when the id set changes.
10. The step summary of `200-build-images.yml`'s `tag-images` job carries a digest for every image, and the `310` release notes list all five.
11. `pip install .` of the monorepo installs no `boto3`; `pip install ".[aws]"` passes the AWS tests.
12. `uv run pytest -q` and `uv run ruff check .` pass; `300-test-codebase.yml` is green on 3.14.

## 20 Validation commands or procedures

Run from the root of a clone of this repository on the branch carrying the change set. Each line is one command; the `# Expected` comment above it says what success looks like, so a real failure can be told from a reporting failure. Docker commands need a running daemon (CI has one; this program's session did not).

PowerShell:

```powershell
# Expected: ruff prints nothing; pytest ends with "passed" and no "failed"
uv python install 3.14; uv sync --all-extras; uv run ruff check .; uv run ruff format --check .; uv run pytest -q
# Expected after B, F, G, D: all three print nothing
git grep -c "def _check_" -- apps/cna-api/main.py; git grep -n "Network Contributor" -- apps cna docs .env.example; git grep -n "ClientSecretCredential|DefaultAzureCredential|sp_client_secret|spSecretEnc|gethostbyname" -- apps cna packages
# Expected: "boundary exit 0 (expected 0)", then ModuleNotFoundError: No module named 'azure' and "import exit 1 (expected 1)"
docker build --build-arg EDITION=lab -t cna:lab .; docker run --rm cna:lab; Write-Host "boundary exit $LASTEXITCODE (expected 0)"; docker run --rm cna:lab python -c "import azure"; Write-Host "import exit $LASTEXITCODE (expected 1)"
# Expected: appliance ok
docker build --build-arg EDITION=appliance -t cna:appliance .; docker run --rm cna:appliance python -c "import azure.identity, azure.mgmt.resourcegraph; print('appliance ok')"
# Expected: the container exits 1 within a few seconds and the log says "forbidden credential variables set"
docker run --rm -e CNA_EDITION=appliance -e AZURE_CLIENT_ID=00000000-0000-0000-0000-000000000001 -e AZURE_CLIENT_SECRET=not-a-real-secret cna:appliance; Write-Host "refusal exit $LASTEXITCODE (expected 1)"
# Expected: 401 (against a running appliance cna-api after H); 200 for /api/health with no token
(Invoke-WebRequest http://127.0.0.1:8080/discovery/jobs/x -SkipHttpErrorCheck).StatusCode; (Invoke-WebRequest http://127.0.0.1:8080/api/health -SkipHttpErrorCheck).StatusCode
# Expected: the rules version, then False
uv build packages/cna-azure-network-engine --out-dir dist; python -m venv .venv-clean; .\.venv-clean\Scripts\pip install (Get-ChildItem dist/*.whl).FullName; .\.venv-clean\Scripts\python -c "import cna_azure_network_engine as e, sys; print(e.RULES_VERSION); print('azure' in sys.modules)"
# Expected once publishing is enabled: one cna_azure_network_engine-*.whl; before that "No matching distribution found" is the expected state, not a build failure
New-Item -ItemType Directory -Force ./wheel | Out-Null; pip download cna-azure-network-engine --no-deps -d ./wheel; Get-ChildItem ./wheel
```

bash (Git Bash or Linux):

```bash
# Expected: ruff prints nothing; pytest ends with "passed" and no "failed"
uv python install 3.14 && uv sync --all-extras && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
# Expected after B, F, G, D: all three print nothing
git grep -c "def _check_" -- apps/cna-api/main.py; git grep -n "Network Contributor" -- apps cna docs .env.example; git grep -n "ClientSecretCredential\|DefaultAzureCredential\|sp_client_secret\|spSecretEnc\|gethostbyname" -- apps cna packages
# Expected: "boundary exit 0 (expected 0)", then ModuleNotFoundError: No module named 'azure' and "import exit 1 (expected 1)"
docker build --build-arg EDITION=lab -t cna:lab . && docker run --rm cna:lab; echo "boundary exit $? (expected 0)"; docker run --rm cna:lab python -c "import azure"; echo "import exit $? (expected 1)"
# Expected: appliance ok
docker build --build-arg EDITION=appliance -t cna:appliance . && docker run --rm cna:appliance python -c "import azure.identity, azure.mgmt.resourcegraph; print('appliance ok')"
# Expected: the container exits 1 within a few seconds and the log says "forbidden credential variables set"
docker run --rm -e CNA_EDITION=appliance -e AZURE_CLIENT_ID=00000000-0000-0000-0000-000000000001 -e AZURE_CLIENT_SECRET=not-a-real-secret cna:appliance; echo "refusal exit $? (expected 1)"
# Expected: 401 (against a running appliance cna-api after H), then 200 for /api/health with no token
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/discovery/jobs/x; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/health
# Expected: the rules version, then False
uv build packages/cna-azure-network-engine --out-dir dist && python -m venv .venv-clean && .venv-clean/bin/pip install dist/*.whl && .venv-clean/bin/python -c "import cna_azure_network_engine as e, sys; print(e.RULES_VERSION); print('azure' in sys.modules)"
# Expected once publishing is enabled: one cna_azure_network_engine-*.whl
mkdir -p ./wheel && pip download cna-azure-network-engine --no-deps -d ./wheel && ls ./wheel
```

Live acceptance (R-008), bash, after `az login` as an identity holding only Reader on the subscriptions named in `CNA_SCOPES`: `CNA_PROFILE=developer uv run cna discover azure --scopes "$CNA_SCOPES"` (the CLI's `AzureCliCredential` path, which the appliance image refuses); expected: the progress log contains no `WARNING` line with `HTTP 403`; record the wall time in `VALIDATION.md`.

## 21 Dependencies on AddOn work

| AddOn item | Relationship to the Core |
|---|---|
| Interim port: `src/network_assessment/model/topology.py` (from `topology_schema.py:315-1010`), `model/findings.py` (`findings_schema.py`), `model/enforcer.py` (`observed_state_enforcer.py` verbatim), `rules/azure_net.py` (Engine A `_check_azure_*` lines 639 to 1660 and Engine B lines 195 to 1127 as `AZ-NET-020..033`), `rules/azure_bcdr.py` (`bcdr_signals.py`), `rules/azure_cost.py` (`finops_signals.py` 001 and 004), `rules/taxonomy.py` (`finding_taxonomy.py`), `classify/topology.py` (`topology_classifier.py`) | Each file carries `# Ported from <the earlier core repository> <path> at 5d3b914; changes: ...`; the AddOn's root `PROVENANCE.md` lists file, source path, commit, lines, changes and reason. The Core's change sets A, B, C and E produce the same symbols under `cna_azure_network_engine`, so the port is removable without semantic change |
| Deletion of the port | When `cna-azure-network-engine` is on PyPI (section 15 step 2), the AddOn's `core-update.yml` pins the exact version, deletes `src/network_assessment/{model,rules,classify}`, keeps `ingestion/`, `store/`, `api/`, `security/`, `web/`, and removes the `PROVENANCE.md` rows for the deleted files |
| Rule ids, severities, `RULES_VERSION`, `TOPOLOGY_MODEL_VERSION` | The AddOn uses the 7.B table and `lab-1.0.0` now; the Core must not renumber. The AddOn's `test_registry.py` hash-pins `RULES_VERSION`; a Core bump is adopted through `core-update` |
| ARG normalizer | The AddOn's `ingestion/normalize.py` (type table in its design B.3) is the reference implementation for the Core's `normalize/resource_graph.py` (C, D); once published, the AddOn imports it too |
| Shared `/api/health` and pane contract | Both builds answer the flat envelope of section 8 with `id: "network-assessment"`; the website's status proxy reads exactly `configured, reachable, version, edition, capabilities, asOf`; the pane posts `{ type: 'hcw-addon', id, state }` with states `loading | ready | working | unavailable` to each `siteOrigins` entry. The Core's appliance public surface uses the same headers and error envelope so one pane bundle serves both builds |
| Build guard | The AddOn's `edition.py` (`sys.meta_path` finder, env refusal) is the model for the Core's lab guard in change set I; the Core may adopt it verbatim with provenance in the other direction |
| Images | AddOn image `docker.io/hybridcloudworks/hcw-addon-network-assessment`; Core images `docker.io/hybridcloudworks/img-ne-appliance-app:*`; both by digest, both through the Docker OIDC connection |

## 22 Open questions and assumptions

**Open questions (owner):**

1. `[REVIEW REQUIRED]` **Relicensing.** Licence decided 2026-10-25 (owner): Apache-2.0 for the code and the image label ([PR 306](https://github.com/saulpatinojr/HCW-NetworkEyes_App/pull/306)); the engine package's `pyproject.toml` now says `license = "Apache-2.0"`. At the commit this plan audited, the Core had no `license` field in `pyproject.toml` and labelled its images `org.opencontainers.image.licenses="Proprietary"` (`Dockerfile:50`); the AddOn is MIT. The copyright holder is decided: Hybrid Cloud Works (owner's statement, 2026-10-26; `LICENSE`, `NOTICE`, `REVIEW.md` R-030). Nothing in this question is open now. The AddOn's `PROVENANCE.md` still makes the ported set removable, and the wheel stays unpublished until the PyPI step in item 2.
2. `[REVIEW REQUIRED]` **PyPI name and trusted publishing.** `cna-azure-network-engine` must be registered on PyPI with a trusted publisher for `saulpatinojr/HCW-NetworkEyes_App` and the `320-release-engine.yml` workflow; `vars.PYPI_PUBLISH_ENABLED` stays unset until then, and the wheel is attached to the GitHub Release instead.
3. **Custom role action names.** Checked on 2026-10-25: the six actions in `docs/roles/cna-network-bgp-reader.json` are listed in the Microsoft Learn Azure permissions reference. Whoever creates the role still re-checks them against their tenant with the `Microsoft.Network` provider operations before `az role definition create`.
4. `[REVIEW REQUIRED]` **Graph and Entra permissions.** The app registration for the bearer audience (7.H) and any Microsoft Graph permission the web tier needs to acquire tokens with its identity are tenant-admin steps.
5. `[REVIEW REQUIRED]` **Compliance-framework references** (WAF, CIS, PCI-DSS, ISO 27001, HIPAA, FedRAMP, CISA ZTMM) carried as rule data from `analysis_engine.py` are claims shown to users; every control reference is `[VERIFY]` and the set needs legal or compliance review before the appliance's anonymous public surface exposes them.
6. **Rule numbering.** Zone-redundancy checks are numbered `AZ-BCDR-006/007` rather than `AZ-NET-02x`, and `AZ-NET-032/033` severities are lowered from Engine B's; both are flagged for the owner, and the AddOn already uses them.
7. **Scale-to-zero.** `min_replicas = 1` is the default; persisting the last snapshot to Blob (UAMI `Storage Blob Data Contributor` on one container) would allow `min_replicas = 0` later `[VERIFY cost]`.
8. **Vendored agent configuration.** Whether the 52 MB under `.agents/`, `.claude/`, `.codex/`, `.kiro/` leaves the product tree is a Core hygiene decision outside the change sets.

**Assumptions:**

| ID | Assumption | If wrong |
|---|---|---|
| A-1 | Core paths equal the `5d3b914` paths (retirement README: created by merging this history) | Section 7 needs a path-mapping pass; validation uses `git grep` for symbols, so the commands still work |
| A-2 | `python:3.14-slim` digest `cae66f2e...` is still the Core's pin or has been bumped deliberately | Use the Core's current pin; the `EDITION` change is independent of the base image |
| A-3 | Resource Graph `Resources`, `ResourceContainers`, `SecurityResources` tables and `skipToken` paging behave as at the time of writing `[VERIFY]` | Adjust the KQL in 7.D; the normalizer contract is unchanged |
| A-4 | Container Apps Consumption `min_replicas = 1` cost is on the order of US$5 to 15 per month `[VERIFY]` | Owner may choose scale-to-zero with a persisted snapshot |
| A-5 | Whoever deploys the appliance applies the Terraform additions of section 12 | This document records the contract and the deployer implements it |
| A-6 | The web tier can obtain a token for the API audience with its user-assigned identity | Fall back to a federated app credential; never a client secret |
| A-7 | Basic Load Balancer and Basic Public IP retirement dates used in rule text are checked: both retired on 30 September 2025 (Microsoft Learn, 2026-10-25) | Text and severity adjusted; ids unchanged |
| A-8 | The AddOn's `lab-1.0.0` model is a strict subset of the engine's `1.3.0` Azure classes | The AddOn's `core-update` PR records the field differences and adapts the normalizer |
