import { describe, expect, it } from "vitest";

import { buildSectionMessages, buildSynthesisMessages, type ReportMeta } from "./report-prompts";
import { buildEnvironmentSnapshot, COMPREHENSIVE_SECTIONS, type SectionSpec } from "./report-sections";

// NetworkEyes is a free tool for followers of Hybrid Cloud Works. The prompts the AI report
// engine sends must not name a company or describe the report as a paid service. These tests
// are the guard that wording drifts past in review (issue #318). `\bclients?\b` does not match
// the field name `clientOrg`, which is a code name and stays.
const BANNED_WORDING =
  /\b(cbts|paid|paying|payments?|pays?|pay for|fees?|consult\w*|customers?|clients?|editions?|invest\w*|malpractice)\b/i;

const META: ReportMeta = {
  clientOrg: "Example Org",
  engagementName: "Example Engagement",
  title: "Cloud Network Assessment",
  date: "2026-10-26",
};

const SPEC: SectionSpec = {
  id: "scope",
  number: 2,
  title: "Scope & Methodology",
  charter: ["Assessed cloud scope", "What was NOT assessed"],
  maxCompletionTokens: 3000,
  slice: () => "slice",
};

// The environment snapshot is part of every section prompt. An empty estate is enough to check
// the fixed text around the data.
const SNAPSHOT = buildEnvironmentSnapshot({
  clientOrg: META.clientOrg,
  engagementName: META.engagementName,
  findings: [],
});

describe("report prompts", () => {
  it("section prompt names no company and no payment", () => {
    const { system, user } = buildSectionMessages(SPEC, "slice text", META, SNAPSHOT);
    expect(system).not.toMatch(BANNED_WORDING);
    expect(user).not.toMatch(BANNED_WORDING);
  });

  it("every real section charter and the environment snapshot are free of that wording", () => {
    expect(COMPREHENSIVE_SECTIONS.length).toBeGreaterThan(0);
    for (const spec of COMPREHENSIVE_SECTIONS) {
      const { system, user } = buildSectionMessages(spec, "slice text", META, SNAPSHOT);
      expect(system, `system prompt of section ${spec.number} ${spec.title}`).not.toMatch(BANNED_WORDING);
      expect(user, `user prompt of section ${spec.number} ${spec.title}`).not.toMatch(BANNED_WORDING);
    }
  });

  it("synthesis prompt names no company and no payment", () => {
    const { system, user } = buildSynthesisMessages(
      META,
      [{ number: 2, title: "Scope & Methodology", summary: "A verdict." }],
      { total: 3, bySeverity: [{ severity: "high", count: 3 }] },
    );
    expect(system).not.toMatch(BANNED_WORDING);
    expect(user).not.toMatch(BANNED_WORDING);
  });

  it("keeps the expert persona and fills in the engagement details", () => {
    const { system } = buildSectionMessages(SPEC, "slice text", META, SNAPSHOT);
    expect(system).toContain("experienced principal network architect");
    expect(system).toContain("Cloud Network Assessment");
    expect(system).toContain(META.clientOrg);
    expect(system).toContain(META.engagementName);
    expect(system).toContain(META.date);
  });

  it("keeps the markers the rest of the app looks for", () => {
    const { system } = buildSectionMessages(SPEC, "slice text", META, SNAPSHOT);
    // app/api/deliverables/[id]/route.ts shows a review banner for these two markers.
    expect(system).toContain("[VERIFY]");
    expect(system).toContain("[REVIEW REQUIRED]");
    expect(system).toContain("<!--SUMMARY:");
  });
});
