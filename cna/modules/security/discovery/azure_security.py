"""Azure security module — wraps Defender for Cloud assessment collection."""

from cna.modules.network.discovery.azure_discovery import AzureDiscovery


def collect_defender_assessments(discovery: AzureDiscovery, sub_id: str):
    """Collect Defender for Cloud network assessments for one subscription.

    Returns list[DefenderAssessment] — same objects stored on AzureSubscriptionTopology.
    Delegates to AzureDiscovery._collect_defender_assessments().
    """
    return discovery._collect_defender_assessments(sub_id)


__all__ = ["collect_defender_assessments"]
