-- DATA-002 / C6: index the per-engagement query path on the highest-volume
-- tables. Postgres does not auto-index FK columns, so every metrics rebuild,
-- report render, chat-context build and dedupe was doing a sequential scan on
-- "engagementId". Plain CREATE INDEX (not CONCURRENTLY): Prisma wraps each
-- migration in a transaction, and CONCURRENTLY cannot run inside one.

-- CreateIndex
CREATE INDEX "IngestedDocument_engagementId_idx" ON "IngestedDocument"("engagementId");

-- CreateIndex
CREATE INDEX "Finding_engagementId_idx" ON "Finding"("engagementId");

-- CreateIndex
CREATE INDEX "DiscoveryJob_engagementId_idx" ON "DiscoveryJob"("engagementId");

-- CreateIndex
CREATE INDEX "Deliverable_engagementId_idx" ON "Deliverable"("engagementId");
