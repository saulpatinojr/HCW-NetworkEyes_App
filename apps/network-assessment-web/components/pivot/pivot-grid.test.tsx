// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import type { StatMasterRecord } from "@/lib/types/stat-master";
import { PivotGrid } from "./pivot-grid";

// Behaviour of the pivot grid on top of TanStack Table. The grid uses only the core row model, so what these tests
// pin down is what a table-library upgrade could silently change: which columns exist, in which order, how a cell
// is formatted, and that the table follows the dimension pickers and the records it is given. They render the real
// component in jsdom; the pivot arithmetic itself belongs to lib/pivot.ts.

function record(over: Partial<StatMasterRecord>): StatMasterRecord {
  return {
    traffic_direction: "east_west",
    severity: "High",
    framework: "CAF",
    region: "westus3",
    subscription_id: "sub-1",
    resource_type: "vnet",
    category: "Network",
    rule_id: "R-1",
    finding_count: 0,
    resource_count: 0,
    est_monthly_cost_impact: 0,
    ...over,
  };
}

const RECORDS: StatMasterRecord[] = [
  record({ category: "Network", severity: "High", finding_count: 3, resource_count: 2, est_monthly_cost_impact: 500 }),
  record({ category: "Network", severity: "Low", finding_count: 1, resource_count: 1, est_monthly_cost_impact: 50 }),
  record({ category: "Storage", severity: "High", finding_count: 5, resource_count: 4, est_monthly_cost_impact: 300 }),
  record({ category: "Compute", severity: "Low", finding_count: 2, resource_count: 2, est_monthly_cost_impact: 10 }),
];

let container: HTMLDivElement;
let root: Root;
let consoleError: MockInstance<typeof console.error>;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  // React reports a duplicate or missing list key through console.error; a spy turns that into a failure.
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  const logged = consoleError.mock.calls.map((args) => args.map(String).join(" "));
  consoleError.mockRestore();
  expect(logged, "React logged an error or warning (for example a duplicate list key)").toEqual([]);
});

function render(ui: React.ReactElement) {
  act(() => root.render(ui));
}

const text = (el: Element) => (el.textContent ?? "").trim();
const cells = (row: Element) => [...row.querySelectorAll("th, td")].map(text);

function headerRow() {
  return cells(container.querySelector("thead tr")!);
}
function bodyRows() {
  return [...container.querySelectorAll("tbody tr")].map(cells);
}
function footerRow() {
  return cells(container.querySelector("tfoot tr")!);
}

function picker(label: string): HTMLSelectElement {
  const wrapper = [...container.querySelectorAll("label")].find((l) => text(l.querySelector("span")!) === label);
  if (!wrapper) throw new Error(`no picker labelled ${label}`);
  return wrapper.querySelector("select")!;
}

function choose(select: HTMLSelectElement, value: string) {
  act(() => {
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("PivotGrid", () => {
  it("renders a header per pivot column and a Total column, with rows ordered by descending total", () => {
    render(<PivotGrid records={RECORDS} />);

    expect(headerRow()).toEqual(["Category", "High", "Low", "Total"]);
    expect(bodyRows()).toEqual([
      ["Storage", "5", "0", "5"],
      ["Network", "3", "1", "4"],
      ["Compute", "0", "2", "2"],
    ]);
    expect(footerRow()).toEqual(["Total", "8", "3", "11"]);
  });

  it("keeps the header, body and footer the same width", () => {
    render(<PivotGrid records={RECORDS} />);
    const width = headerRow().length;
    expect(bodyRows().every((row) => row.length === width)).toBe(true);
    expect(footerRow()).toHaveLength(width);
  });

  it("aligns the first column left and the rest right in the header and in every body row, and styles the row label", () => {
    render(<PivotGrid records={RECORDS} />);
    const headers = [...container.querySelectorAll("thead th")];
    expect(headers[0].className).toContain("text-left");
    expect(headers.slice(1).every((h) => h.className.includes("text-right"))).toBe(true);

    const rows = [...container.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(3);
    for (const row of rows) {
      const tds = [...row.querySelectorAll("td")];
      expect(tds[0].className).toContain("text-left");
      expect(tds[0].className).toContain("pr-4");
      expect(tds.slice(1).every((td) => td.className.includes("text-right") && td.className.includes("pl-4"))).toBe(true);
    }
    expect(container.querySelector("tbody tr td span")?.className).toContain("font-semibold");
  });

  it("logs no React key warning across a picker change, a filter and a data swap", () => {
    render(<PivotGrid records={RECORDS} />);
    choose(picker("Rows"), "severity");
    choose(picker("Columns"), "category");
    choose(picker("Measure"), "est_monthly_cost_impact");
    render(<PivotGrid records={[record({ category: "Identity", severity: "Medium", finding_count: 9 })]} />);
    // afterEach fails the test if console.error was called; make the intent explicit here too.
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("keeps column values named like the grid's own columns apart from them", () => {
    render(
      <PivotGrid
        records={["__row", "__total", "key", "total", "High"].map((severity, i) =>
          record({ severity, finding_count: i + 1 }),
        )}
      />,
    );
    expect(headerRow()).toEqual(["Category", "High", "__row", "__total", "key", "total", "Total"]);
    expect(bodyRows()).toEqual([["Network", "5", "1", "2", "3", "4", "15"]]);
  });

  it("drops the Total column and labels the single value column with the measure when no column dimension is picked", () => {
    render(<PivotGrid records={RECORDS} defaultColumn="" />);

    expect(headerRow()).toEqual(["Category", "Findings"]);
    expect(bodyRows()).toEqual([
      ["Storage", "5"],
      ["Network", "4"],
      ["Compute", "2"],
    ]);
    expect(footerRow()).toEqual(["Total", "11"]);
  });

  it("rebuilds the columns when the row dimension, column dimension or measure changes", () => {
    render(<PivotGrid records={RECORDS} />);

    choose(picker("Rows"), "severity");
    choose(picker("Columns"), "category");
    expect(headerRow()).toEqual(["Severity", "Compute", "Network", "Storage", "Total"]);
    expect(bodyRows()).toEqual([
      ["High", "0", "3", "5", "8"],
      ["Low", "2", "1", "0", "3"],
    ]);

    choose(picker("Columns"), "");
    expect(headerRow()).toEqual(["Severity", "Findings"]);

    choose(picker("Measure"), "resource_count");
    expect(headerRow()).toEqual(["Severity", "Resources"]);
    expect(bodyRows()).toEqual([
      ["High", "6"],
      ["Low", "3"],
    ]);
  });

  it("formats the cost measure as dollars in every cell, the Total column and the footer", () => {
    render(<PivotGrid records={RECORDS} defaultMeasure="est_monthly_cost_impact" />);

    expect(headerRow()).toEqual(["Category", "High", "Low", "Total"]);
    expect(bodyRows()).toEqual([
      ["Network", "$500", "$50", "$550"],
      ["Storage", "$300", "$0", "$300"],
      ["Compute", "$0", "$10", "$10"],
    ]);
    expect(footerRow()).toEqual(["Total", "$800", "$60", "$860"]);
  });

  it("narrows the table to a chosen filter value and widens it again when the chip is removed", () => {
    render(<PivotGrid records={RECORDS} />);

    choose(picker("Filter").parentElement!.querySelector<HTMLSelectElement>('select[aria-label="Add filter value"]')!, "High");
    // One pivot column left, so the grid drops its Total column.
    expect(headerRow()).toEqual(["Category", "High"]);
    expect(bodyRows()).toEqual([
      ["Storage", "5"],
      ["Network", "3"],
    ]);

    const chip = container.querySelector<HTMLButtonElement>('button[aria-label^="Remove filter"]')!;
    expect(chip.getAttribute("aria-label")).toBe("Remove filter Severity: High");
    act(() => chip.click());
    expect(headerRow()).toEqual(["Category", "High", "Low", "Total"]);
    expect(bodyRows()).toHaveLength(3);
  });

  it("follows new records handed in by the parent", () => {
    render(<PivotGrid records={RECORDS} />);
    render(
      <PivotGrid
        records={[record({ category: "Identity", severity: "Medium", finding_count: 9 })]}
      />,
    );

    expect(headerRow()).toEqual(["Category", "Medium"]);
    expect(bodyRows()).toEqual([["Identity", "9"]]);
    expect(footerRow()).toEqual(["Total", "9"]);
  });

  it("shows the empty state and disables the export when nothing matches", () => {
    render(<PivotGrid records={[]} />);

    expect(container.querySelector("table")).toBeNull();
    expect(text(container)).toContain("No records match the current filters.");
    expect(container.querySelector<HTMLButtonElement>("button")?.disabled).toBe(true);
  });
});
