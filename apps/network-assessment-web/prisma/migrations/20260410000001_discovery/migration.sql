-- Migration: add CloudCredential, DiscoveryJob models for live tenant discovery

-- CreateEnum
CREATE TYPE "CloudPlatform" AS ENUM ('AZURE', 'AWS');

-- CreateEnum
CREATE TYPE "DiscoveryJobStatus" AS ENUM ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED');

-- CreateTable
CREATE TABLE "CloudCredential" (
    "id" TEXT NOT NULL,
    "engagementId" TEXT NOT NULL,
    "platform" "CloudPlatform" NOT NULL,
    "label" TEXT NOT NULL,
    "tenantId" TEXT,
    "subscriptionIds" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "spClientId" TEXT,
    "spSecretEnc" TEXT,
    "awsRoleArn" TEXT,
    "awsExternalId" TEXT,
    "awsRegions" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "CloudCredential_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DiscoveryJob" (
    "id" TEXT NOT NULL,
    "engagementId" TEXT NOT NULL,
    "credentialId" TEXT NOT NULL,
    "status" "DiscoveryJobStatus" NOT NULL DEFAULT 'QUEUED',
    "startedAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "errorMessage" TEXT,
    "findingsCount" INTEGER,
    "progressLog" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "DiscoveryJob_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "CloudCredential_engagementId_label_key" ON "CloudCredential"("engagementId", "label");

-- AddForeignKey
ALTER TABLE "CloudCredential" ADD CONSTRAINT "CloudCredential_engagementId_fkey"
    FOREIGN KEY ("engagementId") REFERENCES "Engagement"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DiscoveryJob" ADD CONSTRAINT "DiscoveryJob_engagementId_fkey"
    FOREIGN KEY ("engagementId") REFERENCES "Engagement"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DiscoveryJob" ADD CONSTRAINT "DiscoveryJob_credentialId_fkey"
    FOREIGN KEY ("credentialId") REFERENCES "CloudCredential"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
