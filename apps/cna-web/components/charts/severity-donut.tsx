"use client";

// Client-leaf Recharts severity donut (Phase F).

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { SEVERITY_HEX, SEVERITY_ORDER, CHART_GRID, CBTS_NAVY } from "./chart-theme";

export interface SeverityCount {
  severity: string;
  count: number;
}

export function SeverityDonut({
  data,
  height = 260,
}: {
  data: SeverityCount[];
  height?: number;
}) {
  const ordered = [...data].sort(
    (a, b) =>
      SEVERITY_ORDER.indexOf(a.severity as (typeof SEVERITY_ORDER)[number]) -
      SEVERITY_ORDER.indexOf(b.severity as (typeof SEVERITY_ORDER)[number]),
  );
  const chartData = ordered
    .filter((d) => d.count > 0)
    .map((d) => ({
      name: d.severity === "INFORMATIONAL" ? "Info" : d.severity[0] + d.severity.slice(1).toLowerCase(),
      value: d.count,
      fill: SEVERITY_HEX[d.severity] ?? "#64748b",
    }));

  if (chartData.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={chartData}
          dataKey="value"
          nameKey="name"
          innerRadius="55%"
          outerRadius="80%"
          paddingAngle={2}
          stroke="none"
        >
          {chartData.map((d) => (
            <Cell key={d.name} fill={d.fill} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: CBTS_NAVY, border: `1px solid ${CHART_GRID}`, borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "#fff" }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
