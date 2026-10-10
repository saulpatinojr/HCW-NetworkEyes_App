"""Placeholders for the ``terraform-azure`` and ``terraform-aws`` areas.

The production-readiness review audited the Terraform that used to live under
``infra/terraform/`` in this repository. That layer left the core with
``TODO.md`` T-504: each cloud's Terraform now lives only in its appliance
repository, and the findings the audit recorded were exported there — the AWS
appliance's ``TODO.md`` T-111 and the Azure appliance's ``TODO.md`` T-106 carry
them verbatim, with paths rebased to the appliance layout. The gated
escalations they carried (AWS account, state backend, OIDC role, certificates,
Bedrock opt-in, runtime secrets; the Azure live-acceptance sign-off) are owned by
the appliances' ``REVIEW.md`` files.

The two areas stay in :data:`~cna.review.model.AREAS` — the closed set is part
of the design — so each is represented in the consolidated plan by exactly one
``INFORMATIONAL`` record stating where its review now happens. Nothing here
reads a path; there is no Terraform in this repository to read.
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

AZURE_APPLIANCE = "saulpatinojr/Work-Cloud_Network_Azure_Appliance"
AWS_APPLIANCE = "saulpatinojr/Work-Cloud_Network_AWS_Appliance"


def terraform_relocated_findings() -> list[Finding]:
    """Return the one relocation record per Terraform area."""
    return [
        Finding(
            area="terraform-azure",
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "The Azure Terraform review moved with the deployment layer to "
                f"the Azure appliance repository ({AZURE_APPLIANCE}); its "
                "TODO.md T-106 carries the exported findings and its REVIEW.md "
                "owns the live-acceptance sign-off. No Terraform remains in the "
                "core (TODO.md T-504); review it there."
            ),
            dedup_key="terraform-azure:relocated-to-appliance",
            subject=f"{AZURE_APPLIANCE}:infra/terraform",
        ),
        Finding(
            area="terraform-aws",
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "The AWS Terraform review moved with the deployment layer to "
                f"the AWS appliance repository ({AWS_APPLIANCE}); its TODO.md "
                "T-111 carries the exported findings and its REVIEW.md R-001 – "
                "R-005 and R-008 own the gated escalations (account, state "
                "backend, OIDC role, certificates, Bedrock opt-in, runtime "
                "secrets). No Terraform remains in the core (TODO.md T-504); "
                "review it there."
            ),
            dedup_key="terraform-aws:relocated-to-appliance",
            subject=f"{AWS_APPLIANCE}:infra/terraform",
        ),
    ]
