-- Phase B: finding taxonomy + FinOps fields (additive, nullable)
ALTER TABLE "Finding" ADD COLUMN "trafficDirection" TEXT;
ALTER TABLE "Finding" ADD COLUMN "region" TEXT;
ALTER TABLE "Finding" ADD COLUMN "resourceType" TEXT;
ALTER TABLE "Finding" ADD COLUMN "estCostImpact" DOUBLE PRECISION;
