"use server";

import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { uploadEngagementFile } from "@/lib/blob";
import { analyzeEngagement, type AnalysisFocus } from "@/lib/openai";
import { revalidatePath } from "next/cache";
import type { DocumentType } from "@prisma/client";

// ─── Compliance check ─────────────────────────────────────────────────────────

const ALL_FRAMEWORKS = ["nist", "cis", "soc2", "hipaa", "pci", "waf"] as const;

// Map each compliance framework to the closest available analysis focus
const FRAMEWORK_FOCUS: Record<string, AnalysisFocus> = {
  nist: "compliance_nist",
  cis: "compliance_cis",
  soc2: "compliance_nist",   // NIST 800-53 underpins SOC 2 Trust Services Criteria
  hipaa: "compliance_nist",  // HIPAA technical safeguards map to NIST controls
  pci: "compliance_nist",    // PCI-DSS maps heavily to NIST network controls
  waf: "well_architected",
};

// Framework-specific instructions appended to the user prompt
const FRAMEWORK_HINT: Record<string, string> = {
  soc2: "Additionally, map each finding to the specific SOC 2 Trust Services Criteria (CC6, CC7, CC8, CC9) in the frameworkMapping field.",
  hipaa: "Additionally, map each finding to the specific HIPAA Security Rule citation (45 CFR §164.308, §164.310, or §164.312) in the frameworkMapping field.",
  pci: "Additionally, map each finding to the specific PCI-DSS v4.0 Requirement number (e.g. Req 1.3, Req 6.4) in the frameworkMapping field.",
  waf: "Additionally, map each finding to the specific Azure WAF pillar and design principle in the frameworkMapping field.",
  nist: "",
  cis: "",
};

export async function runComplianceCheck(
  _prev: { error?: string; success?: boolean; count?: number } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean; count?: number }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const engagementId = formData.get("engagementId") as string | null;
  const framework = (formData.get("framework") as string | null) ?? "nist";
  if (!engagementId) return { error: "Missing engagement ID." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const [documents, existingFindings, latestJob] = await Promise.all([
    prisma.ingestedDocument.findMany({
      where: { engagementId, parsedText: { not: null } },
      select: { fileName: true, parsedText: true },
    }),
    prisma.finding.findMany({
      where: { engagementId },
      select: { title: true, severity: true, category: true, description: true },
    }),
    prisma.discoveryJob
      .findFirst({
        where: { engagementId, status: "COMPLETED" },
        orderBy: { completedAt: "desc" },
        select: { topologyJson: true },
      })
      .catch(() => null),
  ]);

  if (!latestJob?.topologyJson && documents.length === 0) {
    return { error: "No data to analyze. Run discovery first or upload documents." };
  }

  const focus = FRAMEWORK_FOCUS[framework] ?? "compliance_nist";
  const hint = FRAMEWORK_HINT[framework] ?? "";

  let rawFindings;
  try {
    rawFindings = await analyzeEngagement({
      topologyJson: latestJob?.topologyJson ?? null,
      documents: documents.map((d) => ({ fileName: d.fileName, text: d.parsedText! })),
      existingFindings,
      focus,
      extraInstruction: hint || undefined,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("[runComplianceCheck][error]", err);
    if (msg.includes("401") || msg.includes("PermissionDenied") || msg.includes("lacks the required")) {
      return { error: "AI analysis failed: the web app is missing the required 'Cognitive Services User' access on the active AI resource." };
    }
    return { error: "Compliance check failed. Check that the active AI engine is reachable, then try again — the full error has been logged." };
  }

  if (rawFindings.length > 0) {
    await prisma.finding.createMany({
      data: rawFindings.map((f) => ({
        engagementId,
        title: f.title,
        severity: f.severity,
        category: f.category,
        description: f.description,
        recommendation: f.recommendation,
        aiGenerated: true,
      })),
    });
  }

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true, count: rawFindings.length };
}

export async function runAllComplianceChecks(
  _prev: { error?: string; success?: boolean; count?: number } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean; count?: number }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const engagementId = formData.get("engagementId") as string | null;
  if (!engagementId) return { error: "Missing engagement ID." };

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const [documents, existingFindings, latestJob] = await Promise.all([
    prisma.ingestedDocument.findMany({
      where: { engagementId, parsedText: { not: null } },
      select: { fileName: true, parsedText: true },
    }),
    prisma.finding.findMany({
      where: { engagementId },
      select: { title: true, severity: true, category: true, description: true },
    }),
    prisma.discoveryJob
      .findFirst({
        where: { engagementId, status: "COMPLETED" },
        orderBy: { completedAt: "desc" },
        select: { topologyJson: true },
      })
      .catch(() => null),
  ]);

  if (!latestJob?.topologyJson && documents.length === 0) {
    return { error: "No data to analyze. Run discovery first or upload documents." };
  }

  const docInput = documents.map((d) => ({ fileName: d.fileName, text: d.parsedText! }));
  const topologyJson = latestJob?.topologyJson ?? null;

  // Run all frameworks in parallel
  const settled = await Promise.allSettled(
    ALL_FRAMEWORKS.map((fw) => {
      const focus = FRAMEWORK_FOCUS[fw] ?? "compliance_nist";
      const hint = FRAMEWORK_HINT[fw] ?? "";
      return analyzeEngagement({
        topologyJson,
        documents: docInput,
        existingFindings,
        focus,
        extraInstruction: hint || undefined,
      });
    }),
  );

  const allRaw = settled.flatMap((r) => (r.status === "fulfilled" ? r.value : []));

  const seen = new Set(existingFindings.map((f) => f.title.toLowerCase()));
  const unique = allRaw.filter((f) => {
    const key = f.title.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (unique.length > 0) {
    await prisma.finding.createMany({
      data: unique.map((f) => ({
        engagementId,
        title: f.title,
        severity: f.severity,
        category: f.category,
        description: f.description,
        recommendation: f.recommendation,
        aiGenerated: true,
      })),
    });
  }

  const failed = settled.filter((r) => r.status === "rejected").length;
  if (failed > 0 && unique.length === 0) {
    return { error: `All ${failed} compliance checks failed. Check active AI engine connectivity.` };
  }

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true, count: unique.length };
}

export async function uploadDocument(
  _prev: { error?: string; success?: boolean } | null,
  formData: FormData,
): Promise<{ error?: string; success?: boolean }> {
  const session = await auth();
  if (!session?.user?.id) return { error: "Not authenticated." };

  const engagementId = formData.get("engagementId") as string | null;
  const docType = formData.get("docType") as string | null;
  const file = formData.get("file") as File | null;

  if (!engagementId || !docType || !file || file.size === 0) {
    return { error: "All fields are required." };
  }

  const member = await prisma.engagementMember.findUnique({
    where: { engagementId_userId: { engagementId, userId: session.user.id } },
  });
  if (!member) return { error: "Access denied." };

  const bytes = await file.arrayBuffer();
  const buffer = Buffer.from(bytes);

  const ext = file.name.toLowerCase().split(".").pop();

  // OWA-06: Server-side MIME & Magic-byte validation to prevent extension spoofing
  const magicBytes = buffer.subarray(0, 4);
  const isPdf = magicBytes[0] === 0x25 && magicBytes[1] === 0x50 && magicBytes[2] === 0x44 && magicBytes[3] === 0x46; // %PDF
  const isPng = magicBytes[0] === 0x89 && magicBytes[1] === 0x50 && magicBytes[2] === 0x4E && magicBytes[3] === 0x47; // \x89PNG
  const isJpeg = magicBytes[0] === 0xFF && magicBytes[1] === 0xD8 && magicBytes[2] === 0xFF; // JPEG SOI

  const allowedTextExts = ["csv", "txt", "json", "yaml", "yml"];
  const isTextExt = ext && allowedTextExts.includes(ext);

  let isValid = isPdf || isPng || isJpeg;
  let parsedText: string | null = null;

  if (!isValid && isTextExt) {
    try {
      // Validate that text files decode cleanly as UTF-8
      parsedText = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      isValid = true;
    } catch {
      isValid = false;
    }
  }

  if (!isValid) {
    return { error: "Invalid file type. Only PDF, PNG, JPEG, CSV, TXT, JSON, and YAML files are allowed." };
  }

  const blobPath = await uploadEngagementFile(
    engagementId,
    file.name,
    buffer,
    file.type || "application/octet-stream",
  );

  await prisma.ingestedDocument.create({
    data: {
      engagementId,
      fileName: file.name,
      blobPath,
      docType: docType as DocumentType,
      parsedText,
    },
  });

  // Advance status from DRAFT → DISCOVERY on first document upload.
  await prisma.engagement.updateMany({
    where: { id: engagementId, status: "DRAFT" },
    data: { status: "DISCOVERY" },
  });

  revalidatePath(`/engagements/${engagementId}`);
  return { success: true };
}
