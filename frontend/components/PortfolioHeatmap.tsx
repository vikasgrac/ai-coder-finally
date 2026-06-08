"use client";
import { formatInr, type Position } from "@/lib/api";

interface PortfolioHeatmapProps {
  positions: Position[];
  onSelectTicker?: (ticker: string) => void;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  ticker: string;
  pct_change: number;
  unrealized_pnl: number;
  quantity: number;
  current_price: number;
}

function squarify(
  items: { ticker: string; value: number; pct_change: number; unrealized_pnl: number; quantity: number; current_price: number }[],
  x: number,
  y: number,
  w: number,
  h: number
): Rect[] {
  if (!items.length) return [];
  if (items.length === 1) {
    return [{ x, y, w, h, ...items[0] }];
  }

  const total = items.reduce((s, i) => s + i.value, 0);
  // Binary split: top half / bottom half
  let cumulative = 0;
  let splitIdx = 0;
  for (let i = 0; i < items.length - 1; i++) {
    cumulative += items[i].value;
    if (cumulative >= total / 2) {
      splitIdx = i + 1;
      break;
    }
    splitIdx = i + 1;
  }

  const first = items.slice(0, splitIdx);
  const second = items.slice(splitIdx);
  const firstFraction = first.reduce((s, i) => s + i.value, 0) / total;

  const rects: Rect[] = [];
  if (w >= h) {
    // Split horizontally
    const w1 = w * firstFraction;
    rects.push(...squarify(first, x, y, w1, h));
    rects.push(...squarify(second, x + w1, y, w - w1, h));
  } else {
    // Split vertically
    const h1 = h * firstFraction;
    rects.push(...squarify(first, x, y, w, h1));
    rects.push(...squarify(second, x, y + h1, w, h - h1));
  }
  return rects;
}

function pnlColor(pct: number): string {
  const abs = Math.abs(pct);
  const intensity = Math.min(abs / 5, 1); // saturate at 5%

  if (pct > 0) {
    const g = Math.round(40 + intensity * 145);
    const r = Math.round(26 - intensity * 10);
    return `rgba(${r}, ${g}, ${Math.round(49 - intensity * 20)}, 0.85)`;
  } else if (pct < 0) {
    const r = Math.round(74 + intensity * 170);
    return `rgba(${r}, ${Math.round(21 - intensity * 10)}, ${Math.round(25 - intensity * 10)}, 0.85)`;
  }
  return "rgba(30, 37, 46, 0.85)";
}

export default function PortfolioHeatmap({ positions, onSelectTicker }: PortfolioHeatmapProps) {
  const items = positions
    .filter((p) => p.quantity > 0)
    .map((p) => ({
      ticker: p.ticker,
      value: p.current_price * p.quantity,
      pct_change: p.pct_change,
      unrealized_pnl: p.unrealized_pnl,
      quantity: p.quantity,
      current_price: p.current_price,
    }))
    .sort((a, b) => b.value - a.value);

  if (!items.length) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#8b949e",
          fontSize: 11,
          fontFamily: '"IBM Plex Mono", monospace',
          letterSpacing: "0.08em",
        }}
      >
        NO POSITIONS
      </div>
    );
  }

  const W = 400;
  const H = 180;
  const rects = squarify(items, 0, 0, W, H);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: "100%", height: "100%", display: "block" }}
      preserveAspectRatio="xMidYMid meet"
    >
      {rects.map((r) => {
        const isSmall = r.w < 50 || r.h < 30;
        const isTiny = r.w < 30 || r.h < 20;
        return (
          <g
            key={r.ticker}
            style={{ cursor: onSelectTicker ? "pointer" : "default" }}
            onClick={() => onSelectTicker?.(r.ticker)}
          >
            <rect
              x={r.x + 1}
              y={r.y + 1}
              width={Math.max(r.w - 2, 0)}
              height={Math.max(r.h - 2, 0)}
              fill={pnlColor(r.pct_change)}
              stroke="#0d1117"
              strokeWidth={1}
              rx={2}
            />
            {!isTiny && (
              <>
                <text
                  x={r.x + r.w / 2}
                  y={r.y + r.h / 2 - (isSmall ? 0 : 8)}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#c9d1d9"
                  fontSize={isSmall ? 8 : 11}
                  fontFamily='"IBM Plex Mono", monospace'
                  fontWeight={600}
                >
                  {r.ticker}
                </text>
                {!isSmall && (
                  <text
                    x={r.x + r.w / 2}
                    y={r.y + r.h / 2 + 8}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={r.pct_change >= 0 ? "#3fb950" : "#f85149"}
                    fontSize={9}
                    fontFamily='"IBM Plex Mono", monospace'
                  >
                    {r.pct_change >= 0 ? "+" : ""}{r.pct_change.toFixed(2)}%
                  </text>
                )}
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
