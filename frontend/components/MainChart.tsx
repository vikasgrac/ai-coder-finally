"use client";
import { formatInr, type PriceUpdate } from "@/lib/api";
import type { PriceHistory } from "@/lib/sse";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface MainChartProps {
  ticker: string | null;
  priceHistory: Record<string, PriceHistory[]>;
  priceCache: Record<string, PriceUpdate>;
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return ts;
  }
}

export default function MainChart({ ticker, priceHistory, priceCache }: MainChartProps) {
  if (!ticker) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#8b949e",
          fontSize: 12,
          fontFamily: '"IBM Plex Mono", monospace',
          letterSpacing: "0.08em",
        }}
      >
        SELECT A TICKER
      </div>
    );
  }

  const history = priceHistory[ticker] ?? [];
  const pd = priceCache[ticker];
  const chartData = history.map((h) => ({
    time: formatTime(h.timestamp),
    price: h.price,
  }));

  const prices = history.map((h) => h.price);
  const firstPrice = prices[0];
  const lastPrice = prices[prices.length - 1] ?? (pd?.price ?? 0);
  const isUp = !firstPrice || lastPrice >= firstPrice;
  const lineColor = isUp ? "#3fb950" : "#f85149";

  const min = prices.length ? Math.min(...prices) : 0;
  const max = prices.length ? Math.max(...prices) : 0;
  const padding = (max - min) * 0.05 || 10;

  const pctChange = firstPrice && firstPrice !== lastPrice
    ? ((lastPrice - firstPrice) / firstPrice * 100)
    : 0;

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        padding: "10px 0 0 0",
      }}
    >
      {/* Ticker header */}
      <div style={{ padding: "0 16px 8px", display: "flex", alignItems: "baseline", gap: 12 }}>
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontWeight: 600,
            fontSize: 16,
            color: "#c9d1d9",
            letterSpacing: "0.06em",
          }}
        >
          {ticker}
        </span>
        {pd && (
          <>
            <span
              style={{
                fontFamily: '"IBM Plex Mono", monospace',
                fontWeight: 500,
                fontSize: 18,
                color: isUp ? "#3fb950" : "#f85149",
              }}
            >
              {formatInr(pd.price)}
            </span>
            <span
              style={{
                fontFamily: '"IBM Plex Mono", monospace',
                fontSize: 12,
                color: pctChange >= 0 ? "#3fb950" : "#f85149",
              }}
            >
              {pctChange >= 0 ? "+" : ""}{pctChange.toFixed(2)}%
            </span>
            <span style={{ color: "#8b949e", fontSize: 11 }}>since page load</span>
          </>
        )}
      </div>

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 0 }}>
        {chartData.length < 2 ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#8b949e",
              fontSize: 11,
              fontFamily: '"IBM Plex Mono", monospace',
            }}
          >
            Streaming prices…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
              <XAxis
                dataKey="time"
                tick={{ fill: "#8b949e", fontSize: 10, fontFamily: '"IBM Plex Mono", monospace' }}
                tickLine={false}
                axisLine={{ stroke: "#30363d" }}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[min - padding, max + padding]}
                tick={{ fill: "#8b949e", fontSize: 10, fontFamily: '"IBM Plex Mono", monospace' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                width={72}
              />
              <Tooltip
                contentStyle={{
                  background: "#161b22",
                  border: "1px solid #30363d",
                  borderRadius: 2,
                  fontFamily: '"IBM Plex Mono", monospace',
                  fontSize: 11,
                  color: "#c9d1d9",
                }}
                formatter={(val) => [formatInr(Number(val)), ticker]}
                labelStyle={{ color: "#8b949e" }}
              />
              {firstPrice && (
                <ReferenceLine y={firstPrice} stroke="#30363d" strokeDasharray="3 3" />
              )}
              <Line
                type="monotone"
                dataKey="price"
                stroke={lineColor}
                strokeWidth={1.5}
                dot={false}
                activeDot={{ r: 3, fill: lineColor, strokeWidth: 0 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
