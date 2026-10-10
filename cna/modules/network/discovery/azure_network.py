"""Azure network module — re-exports AzureDiscovery for Phase C compatibility."""

from cna.modules.network.discovery.azure_discovery import AzureDiscovery

__all__ = ["AzureDiscovery"]
