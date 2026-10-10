"""Findings for the ``app-typescript`` area — AWS-view alignment (Requirement 4.4).

This module records the AWS-view alignment entries for ``apps/cna-web`` demanded
by Requirement 4.4:

    "WHERE the AWS UI views in the Web_Service retain an Azure-shaped
     structure, THE Review_Process SHALL record a Remediation_Plan entry to
     align each view with the AWS deployment model."

It is the companion to spec task 5.1, which recorded the general app-area
type-safety / error-handling findings (F-APP-001 – F-APP-003, now recorded in
``CHANGELOG.md`` → Unreleased → Fixed).
Task 5.2 is scoped specifically to the AWS-view alignment gap, so those entries
live here as structured :class:`~cna.review.model.Finding` records the task-14
consolidation engine can ingest alongside every other area.

Every entry here is a **fixable app-area entry, not an escalation** (design
section "4. Terraform AWS" escalation boundary: *"The AWS-shaped web views (4.4)
are a fixable app-area entry, not an escalation."*). None carries a
``blocker_id``: aligning the views to the AWS deployment model is engineering
work that needs no AWS account, deploy role, or live endpoint. (UI alignment
that depends on the *live* AWS deployment shape — real endpoints/domains —
would reference R-001/R-004 per design section "1. App / TypeScript", but the
structural relabelling recorded here does not.)

Audit result — verify-then-close-gaps
--------------------------------------

The credential-capture view is already platform-aware and correctly
AWS-shaped, and is recorded as verified compliant:

  * **``cloud-credentials/credential-form.tsx`` — verified compliant.** The form
    has a dedicated AWS tab whose fields follow the AWS deployment model
    (Access Key ID, Secret Access Key, read-only Role ARN, External ID, and a
    comma-separated Regions list scoped to a connection label / AWS Org), driven
    by the AWS-specific ``testAwsConnection`` / ``addAwsCredential`` actions and
    an ``arn:aws:iam::...:role/...`` placeholder. The Azure tab keeps the
    tenant/service-principal/subscription shape. No relabelling needed.

The remaining discovery/inventory-facing surfaces still render an
**Azure-shaped structure** for AWS connections and each needs an alignment
entry:

  * **Discovery topology summary (API contract + render).**
    ``app/api/discovery-jobs/[jobId]/route.ts`` derives a ``TopologySummary``
    whose fields are hard-Azure — ``vnets``, ``subnets``, ``firewalls``,
    ``appGateways``, ``dnsZones``, ``expressRoutes``, workload
    ``vmCount/acaCount/aksCount/fnCount``, observability
    ``networkWatchers/logWorkspaces/nsgFlowLogsEnabled`` — parsed from "stored
    AzureTopology JSON" (``sub.vnets`` / ``application_gateways`` /
    ``express_route_circuits`` / ``private_dns_zones``). ``connections-panel.tsx``
    renders those same Azure labels (VNets, AppGWs, ExpressRoute, AKS, "NSG flow
    logs") for **every** completed job regardless of platform, so an AWS
    discovery result is shown under Azure resource names (a VPC labelled
    "VNet", a security group labelled "NSG", a Transit Gateway with no home).

  * **Subscription/tenant framing applied to AWS.** ``connections/page.tsx`` and
    ``discovery/page.tsx`` describe cloud connections purely in the Azure model:
    "Each subscription is a separate sync group", "Removing a subscription also
    removes all its findings", and a per-credential count that reads
    ``subscriptionIds.length`` / "all accessible subscriptions" for AWS
    credentials too — so an AWS org connection displays "0 subscriptions"
    instead of accounts/regions.

  * **Azure-only inventory labelling and connection help.** The engagement
    landing (``app/(dashboard)/engagements/[id]/page.tsx``) advertises Inventory
    as "VNets, NSGs, IPs & resources", and ``components/ui/sp-help-modal.tsx``
    explains connecting only in Azure service-principal terms — neither reflects
    the AWS account/role/region model when an AWS connection is present.

Each Azure-shaped view above is recorded as its own fixable ``Finding`` with a
concrete proposed action to make the surface platform-aware (choose the label
set and count semantics from the credential's ``platform``), so the
consolidation step (spec task 14.1) carries a distinct alignment action per
view.
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

_AREA = "app-typescript"


def _verified_compliant_findings() -> list[Finding]:
    """The credential-capture view is already correctly AWS-shaped (4.4).

    Recorded as ``INFORMATIONAL`` so the plan reflects that the credential
    surface was audited against the AWS deployment model and found aligned,
    not only the surfaces that still need work.
    """
    return [
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: the cloud-credentials CredentialForm has a "
                "dedicated AWS tab following the AWS deployment model (Access Key "
                "ID, Secret Access Key, read-only Role ARN, External ID, "
                "comma-separated Regions, connection label / AWS Org), driven by "
                "testAwsConnection / addAwsCredential and an arn:aws:iam role "
                "placeholder, with the Azure tenant/SP/subscription shape kept on "
                "the Azure tab. No AWS-view relabelling needed; keep the "
                "platform-tabbed form."
            ),
            dedup_key="app-typescript:aws-view-credential-form-aligned",
            subject=(
                "apps/cna-web/app/(dashboard)/engagements/[id]/cloud-credentials/"
                "credential-form.tsx"
            ),
        ),
    ]


def _aws_view_alignment_findings() -> list[Finding]:
    """Requirement 4.4 — one fixable entry per Azure-shaped AWS-facing view."""
    return [
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "Align the discovery topology summary with the AWS deployment "
                "model. The /api/discovery-jobs/[jobId] route derives a "
                "TopologySummary whose fields are hard-Azure (vnets, subnets, "
                "firewalls, appGateways, dnsZones, expressRoutes, "
                "vm/aca/aks/fnCount, networkWatchers/logWorkspaces/nsgFlowLogs) "
                "parsed from AzureTopology JSON, and connections-panel.tsx renders "
                "those Azure labels for every completed job regardless of "
                "platform. Make the summary shape and the JobEntry labels "
                "platform-aware: for an AWS credential surface AWS resources under "
                "AWS names (VPCs, subnets, security groups, route tables, IGW/NAT "
                "gateways, Transit Gateways, Route 53 zones, Direct Connect, "
                "EC2/ECS/EKS/Lambda) instead of relabelling AWS data as VNets / "
                "NSGs / ExpressRoute. Fixable app-area entry; no AWS account "
                "required."
            ),
            dedup_key="app-typescript:aws-view-discovery-topology-summary",
            subject=(
                "apps/cna-web/app/api/discovery-jobs/[jobId]/route.ts, "
                "apps/cna-web/app/(dashboard)/engagements/[id]/connections/"
                "connections-panel.tsx"
            ),
        ),
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "Align the connection/discovery framing with the AWS deployment "
                "model. connections/page.tsx and discovery/page.tsx describe every "
                "cloud connection in Azure terms ('Each subscription is a separate "
                "sync group', 'Removing a subscription', and a per-credential "
                "count of subscriptionIds.length / 'all accessible subscriptions'), "
                "so an AWS org connection reads '0 subscriptions'. Drive the "
                "sync-group wording and the per-credential count from the "
                "credential's platform: for AWS show accounts/regions (and the "
                "role scope) rather than subscriptions/tenant. Fixable app-area "
                "entry; no AWS account required."
            ),
            dedup_key="app-typescript:aws-view-subscription-tenant-framing",
            subject=(
                "apps/cna-web/app/(dashboard)/engagements/[id]/connections/page.tsx, "
                "apps/cna-web/app/(dashboard)/engagements/[id]/discovery/page.tsx"
            ),
        ),
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Align the inventory labelling and connection help with the AWS "
                "deployment model. The engagement landing advertises Inventory as "
                "'VNets, NSGs, IPs & resources' and sp-help-modal.tsx explains "
                "connecting only in Azure service-principal terms. Make the "
                "inventory descriptor platform-neutral (or platform-aware, e.g. "
                "'VPCs, security groups, IPs & resources' for AWS) and give the "
                "connection-help modal an AWS branch covering the access "
                "key + read-only role model so an AWS user sees guidance that "
                "matches the AWS deployment model. Fixable app-area entry; no AWS "
                "account required."
            ),
            dedup_key="app-typescript:aws-view-inventory-label-and-help",
            subject=(
                "apps/cna-web/app/(dashboard)/engagements/[id]/page.tsx, "
                "apps/cna-web/components/ui/sp-help-modal.tsx"
            ),
        ),
    ]


def app_typescript_findings() -> list[Finding]:
    """Return the Requirement 4.4 AWS-view alignment findings for ``apps/cna-web``.

    Combines the verified-compliant credential-capture surface with one fixable
    alignment entry per Azure-shaped AWS-facing view (the discovery topology
    summary, the subscription/tenant connection framing, and the inventory
    label / connection help). Every entry is a fixable app-area finding with no
    ``blocker_id`` — aligning the views to the AWS deployment model needs no AWS
    account. These records are consumed by the consolidation step (spec task
    14.1).
    """
    return _verified_compliant_findings() + _aws_view_alignment_findings()
