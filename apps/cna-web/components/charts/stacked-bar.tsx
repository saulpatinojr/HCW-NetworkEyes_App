"use client";

// Client-leaf Recharts stacked bar (Phase F). Generic: one bar per `category`
// row, stacked by the keys in `series` (e.g. severities).

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";
import { CATEGORY_PALETTE, CHART_GRID, CHART_TEXT, CBTS_NAVY } from "./chart-theme";

export interface StackedBarDatum {
  category: string;
  [seriesKey: string]: string | number;
}

export function StackedBar({
  data,
  series,
  colors,
  height = 280,
  valueFormatter,
}: {
  data: StackedBarDatum[];
  /** Keys of each stacked segment, bottom-up. */
  series: string[];
  /** Optional hex per series key; falls back to CATEGORY_PALETTE. */
  colors?: Record<string, string>;
  height?: number;
  valueFormatter?: (v: number) => string;
}) {
  const fmt = valueFormatter ?? ((v: number) => String(v));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="category"
          tick={{ fill: CHART_TEXT, fontSize: 11 }}
          axisLine={{ stroke: CHART_GRID }}
          tickLine={false}
          interval={0}
          angle={data.length > 5 ? -20 : 0}
          textAnchor={data.length > 5 ? "end" : "middle"}
          height={data.length > 5 ? 56 : 30}
        />
        <YAxis tick={{ fill: CHART_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} width={48} tickFormatter={fmt} />
        <Tooltip
          formatter={(v) => fmt(Number(v))}
          contentStyle={{ background: CBTS_NAVY, border: `1px solid ${CHART_GRID}`, borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "#fff" }}
          cursor={{ fill: "rgba(0,233,187,0.06)" }}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: CHART_TEXT }} />
        {series.map((key, i) => (
          <Bar
            key={key}
            dataKey={key}
            stackId="stack"
            fill={colors?.[key] ?? CATEGORY_PALETTE[i % CATEGORY_PALETTE.length]}
            radius={i === series.length - 1 ? [3, 3, 0, 0] : undefined}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
