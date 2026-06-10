"use client";

// PowerBI-style pivot grid over StatMasterRecords (Phase F).
// Client component: dimension pickers, filter chips, TanStack Table rendering,
// client-side CSV export. Accepts server-fetched or derived records via props.

import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  STAT_DIMENSIONS,
  STAT_MEASURES,
  DIMENSION_LABELS,
  MEASURE_LABELS,
  type StatMasterRecord,
  type StatDimension,
  type StatMeasure,
} from "@/lib/types/stat-master";
import { pivot, pivotToCsv, distinctValues, type PivotFilter, type PivotRow } from "@/lib/pivot";

const selectCls =
  "rounded-lg border border-navy-200 bg-white px-2 py-1.5 text-xs font-medium text-navy-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:border-navy-700 dark:bg-navy-800/60 dark:text-navy-100";

export function PivotGrid({
  records,
  defaultRow = "category",
  defaultColumn = "severity",
  defaultMeasure = "finding_count",
  title = "Pivot Explorer",
}: {
  records: StatMasterRecord[];
  defaultRow?: StatDimension;
  defaultColumn?: StatDimension | "";
  defaultMeasure?: StatMeasure;
  title?: string;
}) {
  const [rowDim, setRowDim] = useState<StatDimension>(defaultRow);
  const [colDim, setColDim] = useState<StatDimension | "">(defaultColumn);
  const [measure, setMeasure] = useState<StatMeasure>(defaultMeasure);
  const [filters, setFilters] = useState<PivotFilter[]>([]);
  const [filterDim, setFilterDim] = useState<StatDimension>("severity");

  const filterValues = useMemo(() => distinctValues(records, filterDim), [records, filterDim]);

  const result = useMemo(
    () =>
      pivot(records, {
        rowDimension: rowDim,
        columnDimension: colDim || undefined,
        measure,
        filters,
      }),
    [records, rowDim, colDim, measure, filters],
  );

  const isCost = measure === "est_monthly_cost_impact";
  const fmt = (v: number) =>
    isCost ? `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : v.toLocaleString();

  const columns = useMemo(() => {
    const helper = createColumnHelper<PivotRow>();
    return [
      helper.accessor("key", {
        id: "__row",
        header: DIMENSION_LABELS[rowDim],
        cell: (info) => (
          <span className="font-semibold text-navy-700 dark:text-navy-100">{info.getValue()}</span>
        ),
      }),
      ...result.columns.map((col) =>
        helper.accessor((row) => row.values[col] ?? 0, {
          id: `col_${col}`,
          header: col === "value" ? MEASURE_LABELS[measure] : col,
          cell: (info) => <span className="tabular-nums">{fmt(info.getValue())}</span>,
        }),
      ),
      ...(result.columns.length > 1
        ? [
            helper.accessor("total", {
              id: "__total",
              header: "Total",
              cell: (info) => (
                <span className="font-bold tabular-nums text-teal-600 dark:text-teal-400">
                  {fmt(info.getValue())}
                </span>
              ),
            }),
          ]
        : []),
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.columns, rowDim, measure, isCost]);

  const table = useReactTable({
    data: result.rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  function addFilter(value: string) {
    if (!value) return;
    if (filters.some((f) => f.dimension === filterDim && f.value === value)) return;
    setFilters((prev) => [...prev, { dimension: filterDim, value }]);
  }

  function removeFilter(idx: number) {
    setFilters((prev) => prev.filter((_, i) => i !== idx));
  }

  function exportCsv() {
    const csv = pivotToCsv(result, DIMENSION_LABELS[rowDim]);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pivot-${rowDim}${colDim ? `-by-${colDim}` : ""}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="glass rounded-xl p-5 print:hidden">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="label-caps text-navy-500">{title}</h2>
        <button
          type="button"
          onClick={exportCsv}
          disabled={result.rows.length === 0}
          className="rounded-lg border border-teal-600/40 px-3 py-1.5 text-xs font-semibold text-teal-600 transition-colors hover:bg-teal-50 disabled:opacity-40 dark:text-teal-400 dark:hover:bg-teal-900/30"
        >
          Export CSV
        </button>
      </div>

      {/* ── Dimension pickers ── */}
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="label-caps text-navy-400">Rows</span>
          <select className={selectCls} value={rowDim} onChange={(e) => setRowDim(e.target.value as StatDimension)}>
            {STAT_DIMENSIONS.map((d) => (
              <option key={d} value={d}>{DIMENSION_LABELS[d]}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-caps text-navy-400">Columns</span>
          <select className={selectCls} value={colDim} onChange={(e) => setColDim(e.target.value as StatDimension | "")}>
            <option value="">— None —</option>
            {STAT_DIMENSIONS.filter((d) => d !== rowDim).map((d) => (
              <option key={d} value={d}>{DIMENSION_LABELS[d]}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-caps text-navy-400">Measure</span>
          <select className={selectCls} value={measure} onChange={(e) => setMeasure(e.target.value as StatMeasure)}>
            {STAT_MEASURES.map((m) => (
              <option key={m} value={m}>{MEASURE_LABELS[m]}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label-caps text-navy-400">Filter</span>
          <div className="flex gap-1.5">
            <select className={selectCls} value={filterDim} onChange={(e) => setFilterDim(e.target.value as StatDimension)}>
              {STAT_DIMENSIONS.map((d) => (
                <option key={d} value={d}>{DIMENSION_LABELS[d]}</option>
              ))}
            </select>
            <select
              className={selectCls}
              value=""
              onChange={(e) => addFilter(e.target.value)}
              aria-label="Add filter value"
            >
              <option value="">+ value…</option>
              {filterValues.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
        </label>
      </div>

      {/* ── Filter chips ── */}
      {filters.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {filters.map((f, i) => (
            <button
              key={`${f.dimension}:${f.value}`}
              type="button"
              onClick={() => removeFilter(i)}
              className="inline-flex items-center gap-1.5 rounded-full border border-teal-600/40 bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-700 transition-colors hover:bg-teal-100 dark:bg-teal-900/30 dark:text-teal-300 dark:hover:bg-teal-900/50"
              aria-label={`Remove filter ${DIMENSION_LABELS[f.dimension]}: ${f.value}`}
            >
              {DIMENSION_LABELS[f.dimension]}: {f.value}
              <span aria-hidden="true">×</span>
            </button>
          ))}
        </div>
      )}

      {/* ── Table ── */}
      {result.rows.length === 0 ? (
        <p className="py-8 text-center text-xs text-navy-500">
          No records match the current filters.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="border-b border-navy-700/40">
                  {hg.headers.map((h, i) => (
                    <th
                      key={h.id}
                      className={`pb-2 ${i === 0 ? "text-left" : "text-right"} font-medium text-navy-500`}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-navy-700/30">
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell, i) => (
                    <td key={cell.id} className={`py-2 ${i === 0 ? "pr-4 text-left" : "pl-4 text-right"} text-navy-300`}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-navy-700/40">
                <td className="py-2 pr-4 font-bold text-navy-200">Total</td>
                {result.columns.map((c) => (
                  <td key={c} className="py-2 pl-4 text-right font-bold tabular-nums text-navy-200">
                    {fmt(result.columnTotals[c] ?? 0)}
                  </td>
                ))}
                {result.columns.length > 1 && (
                  <td className="py-2 pl-4 text-right font-bold tabular-nums text-teal-600 dark:text-teal-400">
                    {fmt(result.grandTotal)}
                  </td>
                )}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
