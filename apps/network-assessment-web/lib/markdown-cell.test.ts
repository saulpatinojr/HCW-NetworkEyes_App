import { describe, expect, it } from "vitest";
import { markdownCell } from "@/lib/markdown-cell";

describe("markdownCell", () => {
  it("passes plain text through and shows a dash for a missing value", () => {
    expect(markdownCell("Public IP uses the Basic SKU", 90)).toBe("Public IP uses the Basic SKU");
    expect(markdownCell(null, 40)).toBe("—");
    expect(markdownCell(undefined, 40)).toBe("—");
  });

  it("escapes pipes and collapses white space and line breaks", () => {
    expect(markdownCell("a | b\n\n c\t d", 90)).toBe("a \\| b c d");
  });

  it("escapes backslashes before pipes, so a trailing backslash cannot swallow the next escape", () => {
    // Input  : x\|y   (a backslash, then a pipe)
    // Output : x\\\|y (an escaped backslash, then an escaped pipe)
    expect(markdownCell("x\\|y", 90)).toBe("x\\\\\\|y");
    expect(markdownCell("ends with \\", 90)).toBe("ends with \\\\");
  });

  it("cuts to the length before escaping, so a cut never leaves a lone escape character", () => {
    const cell = markdownCell("abc\\def", 4); // cut after the backslash
    expect(cell).toBe("abc\\\\");
    expect(cell.replace(/\\\\/g, "")).not.toMatch(/\\$/);
  });
});
