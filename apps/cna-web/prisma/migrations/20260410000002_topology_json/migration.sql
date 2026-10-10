-- Migration: add topologyJson to DiscoveryJob for network inventory page
-- Stores the full AzureTopology JSON from the discovery engine so the
-- inventory page can render resource listings, NSG coverage, and IP inventory
-- without re-running discovery.

ALTER TABLE "DiscoveryJob" ADD COLUMN "topologyJson" TEXT;
