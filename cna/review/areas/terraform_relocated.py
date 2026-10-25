"""Placeholders for the ``terraform-azure`` and ``terraform-aws`` areas.

The production-readiness review audited the Terraform that used to live under
``infra/terraform/`` in this repository. That layer left this repository with
``TODO.md`` T-504: this repository builds and publishes images and contains no
Terraform or deployment workflow, so the Terraform review is not part of this
repository's review. The gated escalations the Terraform carried (AWS account,
state backend, OIDC role, certificates, Bedrock opt-in, runtime secrets; the
Azure live-acceptance sign-off) are not tracked here.

The two areas stay in :data:`~cna.review.model.AREAS` — the closed set is part
of the design — so each is represented in the consolidated plan by exactly one
``INFORMATIONAL`` record stating where its review now happens. Nothing here
reads a path; there is no Terraform in this repository to read.
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

#: Subject prefixes of the two records. They name the deployment layer, not a repository: this repository does
#: not depend on, call or mirror to any repository that deploys its images.
AZURE_DEPLOYMENT_LAYER = "azure-deployment-layer"
AWS_DEPLOYMENT_LAYER = "aws-deployment-layer"


def terraform_relocated_findings() -> list[Finding]:
    """Return the one relocation record per Terraform area."""
    return [
        Finding(
            area="terraform-azure",
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "The Azure Terraform review left with the deployment layer: "
                "this repository builds and publishes images and holds no "
                "Terraform (TODO.md T-504), so there is nothing here to review. "
                "Whoever deploys the images reviews the Azure Terraform and "
                "owns its live-acceptance sign-off."
            ),
            dedup_key="terraform-azure:relocated-to-appliance",
            subject=f"{AZURE_DEPLOYMENT_LAYER}:infra/terraform",
        ),
        Finding(
            area="terraform-aws",
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "The AWS Terraform review left with the deployment layer: this "
                "repository builds and publishes images and holds no Terraform "
                "(TODO.md T-504), so there is nothing here to review. Whoever "
                "deploys the images reviews the AWS Terraform and owns the "
                "gated escalations (account, state backend, OIDC role, "
                "certificates, Bedrock opt-in, runtime secrets)."
            ),
            dedup_key="terraform-aws:relocated-to-appliance",
            subject=f"{AWS_DEPLOYMENT_LAYER}:infra/terraform",
        ),
    ]
