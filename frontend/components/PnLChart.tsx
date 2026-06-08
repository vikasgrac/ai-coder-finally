"use client";
import { useEffect, useState } from "react";
import { api, formatInr, type HistoryPoint } from "@/lib/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function PnLChart({ totalValue }: { totalValue: number }) {
  const [history, setHistory] = useState<HistoryPoint[]>([]);

  const fetchHistory = async () => {
    try {
      const data = await api.getHistory();
      setHistory(data);
    } catch {
      // keep stale
    }
  };

  useEffect(() => {
    fetchHistory();
    const interval = setInterval(fetchHistory, 30000);
    return () => clearInterval(interval);
  }, []);

  const chartData = history.map((h) => ({
    time: formatTime(h.recorded_at),
    value: h.total_value,
  }));

  const values = chartData.map((d) => d.value);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const padding = (max - min) * 0.05 || 500;

  const isUp = !values.length || values[values.length - 1] >= values[0];
  const lineColor = isUp ? "#3fb950" : "#f85149";

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "4px 12px 2px", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: "#8b949e", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Portfolio P&amp;L
        </span>
        <span style={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: 12, color: lineColor }}>
          {formatInr(totalValue)}
        </span>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        {chartData.length < 2 ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#8b949e",
              fontSize: 10,
              fontFamily: '"IBM Plex Mono", monospace',
            }}
          >
            Accumulating data…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
              <XAxis
                dataKey="time"
                tick={{ fill: "#8b949e", fontSize: 9, fontFamily: '"IBM Plex Mono", monospace' }}
                tickLine={false}
                axisLine={{ stroke: "#30363d" }}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[min - padding, max + padding]}
                tick={{ fill: "#8b949e", fontSize: 9, fontFamily: '"IBM Plex Mono", monospace' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
                width={40}
              />
              <Tooltip
                contentStyle={{
                  background: "#161b22",
                  border: "1px solid #30363d",
                  borderRadius: 2,
                  fontFamily: '"IBM Plex Mono", monospace',
                  fontSize: 10,
                  color: "#c9d1d9",
                }}
                formatter={(val) => [formatInr(Number(val)), "Value"]}
                labelStyle={{ color: "#8b949e" }}
              />
              <Line
                type="monotone"
                dataKey="value"
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
