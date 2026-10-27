-- Client-portal publications (CNA-0.90 §3: the publish story). Metadata only —
-- the SAS portal URL is never stored; the API returns it once per publication.
CREATE TABLE "PortalPublication" (
    "id" TEXT NOT NULL,
    "engagementId" TEXT NOT NULL,
    "cloud" TEXT NOT NULL DEFAULT 'azure',
    "storageLocation" TEXT NOT NULL,
    "deliverableCount" INTEGER NOT NULL,
    "ttlHours" INTEGER NOT NULL,
    "issuedAt" TIMESTAMP(3) NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "PortalPublication_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "PortalPublication_engagementId_idx" ON "PortalPublication"("engagementId");

ALTER TABLE "PortalPublication" ADD CONSTRAINT "PortalPublication_engagementId_fkey"
    FOREIGN KEY ("engagementId") REFERENCES "Engagement"("id") ON DELETE CASCADE ON UPDATE CASCADE;
