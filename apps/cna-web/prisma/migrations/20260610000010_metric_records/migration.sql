-- Phase C: stat-master MetricRecord table (additive)
CREATE TABLE "MetricRecord" (
    "id" TEXT NOT NULL,
    "engagementId" TEXT NOT NULL,
    "trafficDirection" TEXT,
    "severity" TEXT,
    "framework" TEXT,
    "region" TEXT,
    "subscriptionId" TEXT,
    "resourceType" TEXT,
    "category" TEXT,
    "ruleId" TEXT,
    "findingCount" INTEGER NOT NULL DEFAULT 0,
    "resourceCount" INTEGER NOT NULL DEFAULT 0,
    "estMonthlyCostImpact" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "MetricRecord_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "MetricRecord_engagementId_idx" ON "MetricRecord"("engagementId");

-- AddForeignKey
ALTER TABLE "MetricRecord" ADD CONSTRAINT "MetricRecord_engagementId_fkey" FOREIGN KEY ("engagementId") REFERENCES "Engagement"("id") ON DELETE CASCADE ON UPDATE CASCADE;
