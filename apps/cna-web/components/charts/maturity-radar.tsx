// Server-renderable SVG maturity radar — extracted from presentation/page.tsx
// and presentation/compliance/page.tsx (Phase F). `size="sm"` reproduces the
// dashboard radar; `size="lg"` reproduces the compliance-page radar (center
// label, larger dots and rings).

import { CBTS_BRIGHT_TEAL, CHART_GRID, CHART_TEXT, CHART_TEXT_DIM } from "./chart-theme";

export interface RadarDim {
  label: string;
  score: number;
}

const SIZES = {
  sm: { cx: 110, cy: 110, R: 72, vb: 220, labelOffset: 22, dotR: 3, fill: "rgba(0,233,187,0.18)", fontSize: 7.5, className: "h-48 w-48", centerLabel: false },
  lg: { cx: 120, cy: 120, R: 88, vb: 240, labelOffset: 28, dotR: 4, fill: "rgba(0,233,187,0.2)", fontSize: 8, className: "h-56 w-56", centerLabel: true },
} as const;

export function MaturityRadar({
  dims,
  size = "sm",
}: {
  dims: RadarDim[];
  size?: keyof typeof SIZES;
}) {
  const { cx, cy, R, vb, labelOffset, dotR, fill, fontSize, className, centerLabel } = SIZES[size];
  const n = dims.length;

  const angleFor = (i: number) => (i * 2 * Math.PI) / n - Math.PI / 2;

  // Axis end-points
  const axes = dims.map((d, i) => ({
    x: cx + R * Math.cos(angleFor(i)),
    y: cy + R * Math.sin(angleFor(i)),
    lx: cx + (R + labelOffset) * Math.cos(angleFor(i)),
    ly: cy + (R + labelOffset) * Math.sin(angleFor(i)),
    label: d.label,
    score: d.score,
  }));

  // Grid rings at 20 / 40 / 60 / 80 / 100 % of R
  const gridRings = [2, 4, 6, 8, 10].map((level) => ({
    level,
    pts: dims
      .map((_, i) => {
        const rr = (level / 10) * R;
        return `${cx + rr * Math.cos(angleFor(i))},${cy + rr * Math.sin(angleFor(i))}`;
      })
      .join(" "),
  }));

  // Data polygon
  const dataPolygon = dims
    .map((d, i) => {
      const rr = (d.score / 10) * R;
      return `${cx + rr * Math.cos(angleFor(i))},${cy + rr * Math.sin(angleFor(i))}`;
    })
    .join(" ");

  return (
    <svg role="img" aria-label="Maturity Radar Chart" viewBox={`0 0 ${vb} ${vb}`} className={className}>
      {/* Grid rings */}
      {gridRings.map(({ level, pts }) => (
        <polygon
          key={level}
          points={pts}
          fill="none"
          stroke={CHART_GRID}
          strokeWidth={centerLabel ? (level === 10 ? 1 : 0.5) : 0.75}
        />
      ))}
      {/* Axes */}
      {axes.map((ax, i) => (
        <line key={i} x1={cx} y1={cy} x2={ax.x} y2={ax.y} stroke={CHART_GRID} strokeWidth="0.75" />
      ))}
      {/* Data fill */}
      <polygon
        points={dataPolygon}
        fill={fill}
        stroke={CBTS_BRIGHT_TEAL}
        strokeWidth="2"
        strokeLinejoin="round"
      />
      {/* Score dots */}
      {dims.map((d, i) => {
        const rr = (d.score / 10) * R;
        const sx = cx + rr * Math.cos(angleFor(i));
        const sy = cy + rr * Math.sin(angleFor(i));
        return <circle key={i} cx={sx} cy={sy} r={dotR} fill={CBTS_BRIGHT_TEAL} />;
      })}
      {/* Axis labels */}
      {axes.map((ax, i) => (
        <text
          key={i}
          x={ax.lx}
          y={ax.ly}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={fontSize}
          fontWeight={centerLabel ? 600 : undefined}
          fill={CHART_TEXT}
        >
          {ax.label}
        </text>
      ))}
      {/* Center label (lg variant only) */}
      {centerLabel && (
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="9" fill={CHART_TEXT_DIM}>
          Maturity
        </text>
      )}
    </svg>
  );
}
