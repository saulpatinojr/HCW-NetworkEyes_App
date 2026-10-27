"""AWS network module — re-exports AWSDiscovery for Phase C compatibility.

Mirrors network_assessment.modules.network.discovery.azure_network, which re-exports
AzureDiscovery. The network topology collection itself lives in aws_discovery.
"""

from network_assessment.modules.network.discovery.aws_discovery import AWSDiscovery

__all__ = ["AWSDiscovery"]
