"use client";
import { formatInr, type Position } from "@/lib/api";

interface PositionsTableProps {
  positions: Position[];
  onSelectTicker?: (ticker: string) => void;
}

export default function PositionsTable({ positions, onSelectTicker }: PositionsTableProps) {
  if (!positions.length) {
    return (
      <div
        style={{
          padding: "16px",
          color: "#8b949e",
          fontSize: 11,
          fontFamily: '"IBM Plex Mono", monospace',
          letterSpacing: "0.06em",
          textAlign: "center",
        }}
      >
        NO OPEN POSITIONS
      </div>
    );
  }

  const thStyle: React.CSSProperties = {
    color: "#8b949e",
    fontSize: 10,
    textTransform: "uppercase",
    letterSpacing: "0.1em",
    fontWeight: 400,
    padding: "4px 8px",
    textAlign: "right",
    borderBottom: "1px solid #30363d",
    background: "#0d1117",
    whiteSpace: "nowrap",
  };

  const tdStyle: React.CSSProperties = {
    fontFamily: '"IBM Plex Mono", monospace',
    fontSize: 11,
    padding: "4px 8px",
    borderBottom: "1px solid rgba(48,54,61,0.4)",
    textAlign: "right",
    whiteSpace: "nowrap",
  };

  return (
    <div style={{ overflowX: "auto", height: "100%" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 11,
        }}
      >
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: "left" }}>Symbol</th>
            <th style={thStyle}>Qty</th>
            <th style={thStyle}>Avg Cost</th>
            <th style={thStyle}>Cur Price</th>
            <th style={thStyle}>Unreal P&amp;L</th>
            <th style={thStyle}>% Chg</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => {
            const isUp = pos.unrealized_pnl >= 0;
            const pnlColor = isUp ? "#3fb950" : "#f85149";
            return (
              <tr
                key={pos.ticker}
                className="hover-row"
                style={{ cursor: onSelectTicker ? "pointer" : "default" }}
                onClick={() => onSelectTicker?.(pos.ticker)}
              >
                <td style={{ ...tdStyle, textAlign: "left" }}>
                  <span
                    style={{
                      fontWeight: 600,
                      color: "#c9d1d9",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {pos.ticker}
                  </span>
                </td>
                <td style={{ ...tdStyle, color: "#c9d1d9" }}>
                  {pos.quantity.toLocaleString("en-IN")}
                </td>
                <td style={{ ...tdStyle, color: "#8b949e" }}>
                  {formatInr(pos.avg_cost)}
                </td>
                <td style={{ ...tdStyle, color: "#c9d1d9" }}>
                  {formatInr(pos.current_price)}
                </td>
                <td style={{ ...tdStyle, color: pnlColor }}>
                  {pos.unrealized_pnl >= 0 ? "+" : ""}{formatInr(pos.unrealized_pnl)}
                </td>
                <td
                  style={{
                    ...tdStyle,
                    color: pnlColor,
                    fontWeight: 500,
                  }}
                >
                  {pos.pct_change >= 0 ? "+" : ""}{pos.pct_change.toFixed(2)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
