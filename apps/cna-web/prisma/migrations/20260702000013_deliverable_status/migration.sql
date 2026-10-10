-- Sectioned Comprehensive Assessment: background generation status + progress (additive)
CREATE TYPE "DeliverableStatus" AS ENUM ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED');

ALTER TABLE "Deliverable"
  ADD COLUMN "status" "DeliverableStatus" NOT NULL DEFAULT 'COMPLETED',
  ADD COLUMN "progressLog" TEXT;
