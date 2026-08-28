// Server-renderable SVG risk gauge — extracted from presentation/page.tsx (Phase F).
// Rendering is identical to the original inline component.

import { CHART_GRID, CHART_TEXT_DIM } from "./chart-theme";

export function RiskGauge({ score, color }: { score: number; color: string }) {
  const r = 68;
  const circ = 2 * Math.PI * r;            // ≈ 427.3
  const arcLen = (270 / 360) * circ;       // ≈ 320.5  (270° sweep)
  const filled = (score / 100) * arcLen;

  return (
    <svg viewBox="0 0 180 180" className="h-44 w-44 text-navy-800 dark:text-navy-100">
      {/* Track */}
      <circle
        cx="90" cy="90" r={r}
        fill="none"
        stroke={CHART_GRID}
        strokeWidth="14"
        strokeLinecap="round"
        strokeDasharray={`${arcLen} ${circ}`}
        transform="rotate(-135 90 90)"
      />
      {/* Value arc */}
      <circle
        cx="90" cy="90" r={r}
        fill="none"
        stroke={color}
        strokeWidth="14"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circ}`}
        transform="rotate(-135 90 90)"
      />
      {/* Score */}
      <text
        x="90" y="88"
        textAnchor="middle"
        fontSize="38"
        fontWeight="900"
        fill="currentColor"
      >
        {score}
      </text>
      <text
        x="90" y="110"
        textAnchor="middle"
        fontSize="9"
        fill={CHART_TEXT_DIM}
        letterSpacing="1"
      >
        RISK SCORE
      </text>
    </svg>
  );
}
