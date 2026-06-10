"use client";

// Client-leaf Recharts traffic-direction breakdown (Phase F):
// one bar per traffic direction, stacked by severity.

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
import {
  SEVERITY_HEX,
  SEVERITY_ORDER,
  TRAFFIC_DIRECTION_LABELS,
  CHART_GRID,
  CHART_TEXT,
  CBTS_NAVY,
} from "./chart-theme";

export interface TrafficBreakdownDatum {
  /** east_west | north_south | management | unclassified */
  direction: string;
  /** severity → finding count */
  counts: Record<string, number>;
}

export function TrafficBreakdown({
  data,
  height = 280,
}: {
  data: TrafficBreakdownDatum[];
  height?: number;
}) {
  const chartData = data.map((d) => ({
    direction: TRAFFIC_DIRECTION_LABELS[d.direction] ?? d.direction,
    ...d.counts,
  }));

  const presentSeverities = SEVERITY_ORDER.filter((sev) =>
    data.some((d) => (d.counts[sev] ?? 0) > 0),
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="direction"
          tick={{ fill: CHART_TEXT, fontSize: 11 }}
          axisLine={{ stroke: CHART_GRID }}
          tickLine={false}
        />
        <YAxis tick={{ fill: CHART_TEXT, fontSize: 11 }} axisLine={false} tickLine={false} width={40} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: CBTS_NAVY, border: `1px solid ${CHART_GRID}`, borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "#fff" }}
          cursor={{ fill: "rgba(0,233,187,0.06)" }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {presentSeverities.map((sev, i) => (
          <Bar
            key={sev}
            dataKey={sev}
            name={sev === "INFORMATIONAL" ? "Info" : sev[0] + sev.slice(1).toLowerCase()}
            stackId="sev"
            fill={SEVERITY_HEX[sev]}
            radius={i === presentSeverities.length - 1 ? [3, 3, 0, 0] : undefined}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
