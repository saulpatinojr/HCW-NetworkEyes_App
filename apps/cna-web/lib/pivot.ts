// ──────────────────────────────────────────────────────────────────────────────
// Pure pivot / aggregation helpers over StatMasterRecord (Phase F).
// No I/O, no React — unit-testable.
// ──────────────────────────────────────────────────────────────────────────────

import type { StatMasterRecord, StatDimension, StatMeasure } from "./types/stat-master";

export interface PivotFilter {
  dimension: StatDimension;
  value: string;
}

export interface PivotRow {
  /** Value of the row dimension for this row. */
  key: string;
  /** Column key → aggregated measure. When no column dimension, single key "value". */
  values: Record<string, number>;
  /** Row total across all columns. */
  total: number;
}

export interface PivotResult {
  rows: PivotRow[];
  /** Distinct column keys, sorted. ["value"] when no column dimension. */
  columns: string[];
  /** Column key → column total. */
  columnTotals: Record<string, number>;
  grandTotal: number;
}

/** Apply dimension=value filters (AND across dimensions, OR within a dimension). */
export function applyFilters(
  records: StatMasterRecord[],
  filters: PivotFilter[],
): StatMasterRecord[] {
  if (filters.length === 0) return records;
  const byDim = new Map<StatDimension, Set<string>>();
  for (const f of filters) {
    if (!byDim.has(f.dimension)) byDim.set(f.dimension, new Set());
    byDim.get(f.dimension)!.add(f.value);
  }
  return records.filter((r) =>
    [...byDim.entries()].every(([dim, values]) => values.has(String(r[dim]))),
  );
}

/** Sum a measure grouped by a single dimension. */
export function groupBy(
  records: StatMasterRecord[],
  dimension: StatDimension,
  measure: StatMeasure,
): { key: string; value: number }[] {
  const acc = new Map<string, number>();
  for (const r of records) {
    const key = String(r[dimension]);
    acc.set(key, (acc.get(key) ?? 0) + (r[measure] ?? 0));
  }
  return [...acc.entries()]
    .map(([key, value]) => ({ key, value }))
    .sort((a, b) => b.value - a.value);
}

/** Distinct values of a dimension, sorted alphabetically. */
export function distinctValues(
  records: StatMasterRecord[],
  dimension: StatDimension,
): string[] {
  return [...new Set(records.map((r) => String(r[dimension])))].sort();
}

/**
 * Pivot: aggregate `measure` by `rowDimension` (rows) × optional
 * `columnDimension` (columns). Rows sorted by descending total.
 */
export function pivot(
  records: StatMasterRecord[],
  opts: {
    rowDimension: StatDimension;
    columnDimension?: StatDimension;
    measure: StatMeasure;
    filters?: PivotFilter[];
  },
): PivotResult {
  const filtered = applyFilters(records, opts.filters ?? []);
  const { rowDimension, columnDimension, measure } = opts;

  const rowMap = new Map<string, Record<string, number>>();
  const columnSet = new Set<string>();

  for (const r of filtered) {
    const rowKey = String(r[rowDimension]);
    const colKey = columnDimension ? String(r[columnDimension]) : "value";
    columnSet.add(colKey);
    if (!rowMap.has(rowKey)) rowMap.set(rowKey, {});
    const row = rowMap.get(rowKey)!;
    row[colKey] = (row[colKey] ?? 0) + (r[measure] ?? 0);
  }

  const columns = [...columnSet].sort();
  const rows: PivotRow[] = [...rowMap.entries()]
    .map(([key, values]) => ({
      key,
      values,
      total: Object.values(values).reduce((s, v) => s + v, 0),
    }))
    .sort((a, b) => b.total - a.total);

  const columnTotals: Record<string, number> = {};
  for (const col of columns) {
    columnTotals[col] = rows.reduce((s, r) => s + (r.values[col] ?? 0), 0);
  }
  const grandTotal = rows.reduce((s, r) => s + r.total, 0);

  return { rows, columns, columnTotals, grandTotal };
}

/** Serialize a pivot result to CSV (header row + data rows + totals row). */
export function pivotToCsv(result: PivotResult, rowLabel: string): string {
  const esc = (v: string | number) => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = [rowLabel, ...result.columns.map((c) => (c === "value" ? "Value" : c)), "Total"];
  const lines = [header.map(esc).join(",")];
  for (const row of result.rows) {
    lines.push(
      [row.key, ...result.columns.map((c) => row.values[c] ?? 0), row.total].map(esc).join(","),
    );
  }
  lines.push(
    ["Total", ...result.columns.map((c) => result.columnTotals[c] ?? 0), result.grandTotal]
      .map(esc)
      .join(","),
  );
  return lines.join("\n");
}
