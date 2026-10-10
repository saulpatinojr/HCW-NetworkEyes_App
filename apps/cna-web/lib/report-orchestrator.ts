// ──────────────────────────────────────────────────────────────────────────────
// Multi-pass orchestrator for the Comprehensive Assessment deliverable.
// Runs one AI call per report section (batched for TPM headroom), a synthesis
// pass for the Executive Summary, then assembles the final Markdown document
// with deterministic appendices. Sections that fail twice degrade to a
// [REVIEW REQUIRED] placeholder instead of failing the whole report.
// ──────────────────────────────────────────────────────────────────────────────

import { generateAiCompletion } from "@/lib/ai-engine";
import type { DeliverableContext } from "@/lib/openai";
import { fetchMsLearnContext, summarizeTopology } from "@/lib/openai";
import {
  ABBREVIATIONS,
  buildEnvironmentSnapshot,
  COMPREHENSIVE_SECTIONS,
  inventoryCounts,
  type ReportFinding,
  type SectionInput,
  type SectionSpec,
} from "@/lib/report-sections";
import {
  buildSectionMessages,
  buildSynthesisMessages,
  SUMMARY_TRAILER_RE,
  type ReportMeta,
} from "@/lib/report-prompts";

export type SectionStatus = "pending" | "running" | "done" | "failed" | "skipped";

export interface ProgressUpdate {
  stepId: string;
  label: string;
  status: SectionStatus;
}

export type ProgressCallback = (update: ProgressUpdate) => Promise<void> | void;

const BATCH_SIZE = 2; // concurrent section calls — sized against deployment TPM
const RETRY_DELAY_MS = 5_000;

const SEV_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"];

interface SectionResult {
  spec: SectionSpec;
  markdown: string;
  summary: string | null;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runSection(
  spec: SectionSpec,
  input: SectionInput,
  meta: ReportMeta,
  environmentSnapshot: string,
  msLearnContext: string,
  onProgress?: ProgressCallback,
): Promise<SectionResult> {
  const slice = spec.slice(input);
  if (!slice) {
    await onProgress?.({ stepId: spec.id, label: spec.title, status: "skipped" });
    return {
      spec,
      markdown: `## ${spec.number}. ${spec.title}\n\nNo findings or discovery data relevant to this domain were captured during the assessment window, so it was not assessed in depth. Confirm with the client whether this domain is in scope for a follow-up. [REVIEW REQUIRED]`,
      summary: `${spec.title}: no relevant data captured; domain not assessed.`,
    };
  }

  await onProgress?.({ stepId: spec.id, label: spec.title, status: "running" });
  const { system, user } = buildSectionMessages(spec, slice, meta, environmentSnapshot, msLearnContext);

  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const raw = await generateAiCompletion({
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
        maxCompletionTokens: spec.maxCompletionTokens,
      });
      if (!raw?.trim()) throw new Error("empty completion");

      const summaryMatch = SUMMARY_TRAILER_RE.exec(raw);
      const markdown = raw.replace(SUMMARY_TRAILER_RE, "").trim();
      await onProgress?.({ stepId: spec.id, label: spec.title, status: "done" });
      return { spec, markdown, summary: summaryMatch?.[1]?.trim() ?? null };
    } catch (err) {
      if (attempt === 1) {
        await delay(RETRY_DELAY_MS);
        continue;
      }
      console.error(`[report-orchestrator] section ${spec.id} failed twice:`, err);
      await onProgress?.({ stepId: spec.id, label: spec.title, status: "failed" });
      return {
        spec,
        markdown: `## ${spec.number}. ${spec.title}\n\n*This section is pending review — automated generation did not complete. Regenerate the assessment or author this section manually before publishing.*`,
        summary: `${spec.title}: generation failed; section requires manual authoring.`,
      };
    }
  }
  throw new Error("unreachable");
}

// ── Deterministic appendices ──────────────────────────────────────────────────

function findingsRegister(findings: ReportFinding[]): string {
  const rows = [...findings].sort(
    (a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity),
  );
  const lines = [
    "## Appendix A. Findings Register",
    "",
    `Complete register of all ${rows.length} findings evaluated in this assessment.`,
    "",
    "| # | Severity | Category | Finding | Recommendation |",
    "|---|----------|----------|---------|----------------|",
  ];
  const clean = (s: string | null | undefined, max: number) =>
    (s ?? "—").replace(/\|/g, "\\|").replace(/\s+/g, " ").slice(0, max);
  rows.forEach((f, i) => {
    lines.push(
      `| ${i + 1} | ${f.severity} | ${clean(f.category, 40)} | ${clean(f.title, 90)} | ${clean(f.recommendation, 160)} |`,
    );
  });
  return lines.join("\n");
}

function inventoryAppendix(topologyJson?: string | null): string {
  const inv = inventoryCounts(topologyJson);
  const lines = ["## Appendix B. Discovered Inventory", ""];
  if (!inv.length) {
    lines.push("No live-discovery topology was available when this report was generated.");
    return lines.join("\n");
  }
  for (const row of inv) {
    lines.push(`### Subscription: ${row.subscription}`, "", "| Resource type | Count |", "|---|---|");
    for (const c of row.counts) lines.push(`| ${c.label} | ${c.count} |`);
    lines.push("");
  }
  return lines.join("\n");
}

function referencesAppendix(sectionMarkdown: string[]): string {
  const urls = new Set<string>();
  const re = /https:\/\/learn\.microsoft\.com\/[^\s)\]"'<>]+/g;
  for (const md of sectionMarkdown) {
    for (const m of md.match(re) ?? []) urls.add(m.replace(/[.,;]+$/, ""));
  }
  const lines = ["## Appendix C. References", ""];
  if (!urls.size) {
    lines.push("No external references were cited in this report.");
  } else {
    lines.push("Microsoft Learn documentation cited in this report:", "");
    for (const u of [...urls].sort()) lines.push(`- [${u}](${u})`);
  }
  return lines.join("\n");
}

function abbreviationsAppendix(): string {
  const lines = ["## Appendix D. Abbreviations", "", "| Abbreviation | Meaning |", "|---|---|"];
  for (const [abbr, meaning] of ABBREVIATIONS) lines.push(`| ${abbr} | ${meaning} |`);
  return lines.join("\n");
}

// ── Main entry point ──────────────────────────────────────────────────────────

export async function generateComprehensiveReport(
  ctx: DeliverableContext,
  onProgress?: ProgressCallback,
): Promise<string> {
  const date = new Date().toISOString().split("T")[0];
  const meta: ReportMeta = {
    clientOrg: ctx.clientOrg,
    engagementName: ctx.engagementName,
    title: ctx.title,
    date,
  };

  const findings = ctx.findings as unknown as ReportFinding[];
  const input: SectionInput = {
    clientOrg: ctx.clientOrg,
    engagementName: ctx.engagementName,
    findings,
    topologyJson: ctx.topologyJson,
    topologySummary: ctx.topologyJson ? summarizeTopology(ctx.topologyJson) : null,
    credentialsInfo: ctx.credentialsInfo,
    documents: ctx.documents,
  };

  // Shared MS Learn enrichment — fetched once, given to every section.
  const categories = [...new Set(findings.map((f) => f.category))];
  const msLearnContext = await fetchMsLearnContext(categories);

  // Deterministic whole-estate snapshot: sections run in parallel and can't
  // see each other's prose — this shared context is what makes twelve
  // independent calls narrate one network.
  const environmentSnapshot = buildEnvironmentSnapshot(input);

  // ── Domain sections in batches ─────────────────────────────────────────────
  const results: SectionResult[] = [];
  for (let i = 0; i < COMPREHENSIVE_SECTIONS.length; i += BATCH_SIZE) {
    const batch = COMPREHENSIVE_SECTIONS.slice(i, i + BATCH_SIZE);
    const settled = await Promise.allSettled(
      batch.map((spec) => runSection(spec, input, meta, environmentSnapshot, msLearnContext, onProgress)),
    );
    for (const s of settled) {
      // runSection handles its own failures — a rejection here is a bug guard.
      if (s.status === "fulfilled") results.push(s.value);
    }
  }
  results.sort((a, b) => a.spec.number - b.spec.number);

  // ── Synthesis pass: Executive Summary ──────────────────────────────────────
  await onProgress?.({ stepId: "executive", label: "Executive Summary", status: "running" });
  const bySeverity = SEV_ORDER.map((s) => ({
    severity: s,
    count: findings.filter((f) => f.severity === s).length,
  })).filter((x) => x.count > 0);

  let execSummary: string;
  try {
    const { system, user } = buildSynthesisMessages(
      meta,
      results.map((r) => ({
        number: r.spec.number,
        title: r.spec.title,
        summary: r.summary ?? "(no summary available)",
      })),
      { total: findings.length, bySeverity },
    );
    execSummary = (
      await generateAiCompletion({
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
        maxCompletionTokens: 3000,
      })
    )?.trim() || "";
    if (!execSummary) throw new Error("empty completion");
    await onProgress?.({ stepId: "executive", label: "Executive Summary", status: "done" });
  } catch (err) {
    console.error("[report-orchestrator] executive summary failed:", err);
    execSummary = `## 1. Executive Summary\n\n[REVIEW REQUIRED] Automated synthesis of the executive summary failed. Author this section manually from the domain sections below before publishing.`;
    await onProgress?.({ stepId: "executive", label: "Executive Summary", status: "failed" });
  }

  // ── Assembly ───────────────────────────────────────────────────────────────
  await onProgress?.({ stepId: "assembly", label: "Document assembly", status: "running" });

  const titleBlock = [
    `# ${ctx.title}`,
    "",
    `**Client:** ${ctx.clientOrg}  `,
    `**Engagement:** ${ctx.engagementName}  `,
    `**Date:** ${date}  `,
    `**Prepared by:** CBTS Cloud Security Practice  `,
    `**Classification:** Client Confidential`,
    "",
    "> This assessment was generated from live-discovered topology and analysis findings. Content flagged [VERIFY] or [REVIEW REQUIRED] must be validated by the engagement team before client delivery.",
  ].join("\n");

  const sectionBodies = results.map((r) => r.markdown);
  const document = [
    titleBlock,
    execSummary,
    ...sectionBodies,
    findingsRegister(findings),
    inventoryAppendix(ctx.topologyJson),
    referencesAppendix([execSummary, ...sectionBodies]),
    abbreviationsAppendix(),
  ].join("\n\n---\n\n");

  await onProgress?.({ stepId: "assembly", label: "Document assembly", status: "done" });
  return document;
}
