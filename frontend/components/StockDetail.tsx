"use client";
import { useEffect, useState, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { api, formatInr, type PriceUpdate, type StockHistoryPoint } from "@/lib/api";
import type { PriceHistory } from "@/lib/sse";

type Period = "1d" | "1w" | "1m" | "6m" | "1y" | "5y";

const PERIODS: { key: Period; label: string }[] = [
  { key: "1d", label: "1D" },
  { key: "1w", label: "1W" },
  { key: "1m", label: "1M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
  { key: "5y", label: "5Y" },
];

interface StockDetailProps {
  ticker: string | null;
  priceHistory: Record<string, PriceHistory[]>;
  priceCache: Record<string, PriceUpdate>;
}

interface QuoteStat {
  week52High: number;
  week52Low: number;
  volume: number | null;
  buyVol: number | null;
  sellVol: number | null;
}

function fmt(n: number | null, decimals = 0): string {
  if (n === null) return "—";
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtVol(n: number | null): string {
  if (n === null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatLabel(ts: string, period: Period): string {
  try {
    const d = new Date(ts);
    if (period === "1d") {
      return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
    }
    if (period === "1w") {
      return d.toLocaleString("en-IN", { weekday: "short", hour: "2-digit", minute: "2-digit" });
    }
    if (period === "5y") {
      return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
    }
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch {
    return ts;
  }
}

export default function StockDetail({ ticker, priceHistory, priceCache }: StockDetailProps) {
  const [period, setPeriod] = useState<Period>("1d");
  const [fetchedHistory, setFetchedHistory] = useState<StockHistoryPoint[] | null>(null);
  const [quote, setQuote] = useState<QuoteStat | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchHistory = useCallback(async (t: string, p: Period) => {
    if (p === "1d") {
      setFetchedHistory(null); // use SSE data
      return;
    }
    setLoading(true);
    try {
      const data = await api.getStockHistory(t, p);
      setFetchedHistory(data);
    } catch {
      setFetchedHistory(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchQuote = useCallback(async (t: string) => {
    try {
      const q = await api.getStockQuote(t);
      setQuote({
        week52High: q.week_52_high,
        week52Low: q.week_52_low,
        volume: q.prev_day_volume,
        buyVol: q.prev_day_buy_volume,
        sellVol: q.prev_day_sell_volume,
      });
    } catch {
      setQuote(null);
    }
  }, []);

  useEffect(() => {
    if (!ticker) return;
    setPeriod("1d");
    setFetchedHistory(null);
    fetchQuote(ticker);
  }, [ticker, fetchQuote]);

  useEffect(() => {
    if (!ticker) return;
    fetchHistory(ticker, period);
  }, [ticker, period, fetchHistory]);

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

  const pd = priceCache[ticker];

  // Build chart data
  const ssePoints: StockHistoryPoint[] = (priceHistory[ticker] ?? []).map((h) => ({
    time: h.timestamp,
    price: h.price,
  }));
  const chartPoints: StockHistoryPoint[] =
    period === "1d" ? ssePoints : (fetchedHistory ?? []);

  const prices = chartPoints.map((p) => p.price);
  const firstPrice = prices[0];
  const lastPrice = prices[prices.length - 1] ?? pd?.price ?? 0;
  const isUp = !firstPrice || lastPrice >= firstPrice;
  const lineColor = isUp ? "#3fb950" : "#f85149";
  const pctChange =
    firstPrice && firstPrice !== lastPrice
      ? ((lastPrice - firstPrice) / firstPrice) * 100
      : 0;

  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 0;
  const pad = (maxP - minP) * 0.06 || lastPrice * 0.01;

  const chartData = chartPoints.map((p) => ({
    time: formatLabel(p.time, period),
    price: p.price,
  }));

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        minHeight: 0,
        background: "#0d1117",
      }}
    >
      {/* ── Header: ticker + price + change ── */}
      <div
        style={{
          padding: "10px 16px 6px",
          display: "flex",
          alignItems: "baseline",
          gap: 12,
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontWeight: 700,
            fontSize: 15,
            color: "#c9d1d9",
            letterSpacing: "0.08em",
          }}
        >
          {ticker}
        </span>
        {pd && (
          <>
            <span
              style={{
                fontFamily: '"IBM Plex Mono", monospace',
                fontWeight: 600,
                fontSize: 20,
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
              {pctChange >= 0 ? "▲" : "▼"} {Math.abs(pctChange).toFixed(2)}%
              <span style={{ color: "#8b949e", marginLeft: 6, fontSize: 10 }}>
                since page load
              </span>
            </span>
          </>
        )}
      </div>

      {/* ── Stats bar: 52W High/Low + Volume ── */}
      <div
        style={{
          display: "flex",
          gap: 0,
          padding: "0 16px 6px",
          flexShrink: 0,
          flexWrap: "wrap",
          rowGap: 4,
        }}
      >
        {[
          { label: "52W High", value: quote ? formatInr(quote.week52High) : "—" },
          { label: "52W Low",  value: quote ? formatInr(quote.week52Low) : "—" },
          { label: "Prev Vol", value: fmtVol(quote?.volume ?? null) },
          { label: "Buy Vol",  value: fmtVol(quote?.buyVol ?? null), color: "#3fb950" },
          { label: "Sell Vol", value: fmtVol(quote?.sellVol ?? null), color: "#f85149" },
        ].map(({ label, value, color }) => (
          <div
            key={label}
            style={{
              marginRight: 20,
              display: "flex",
              flexDirection: "column",
              gap: 1,
            }}
          >
            <span
              style={{
                color: "#8b949e",
                fontSize: 9,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                fontFamily: '"IBM Plex Sans", sans-serif',
              }}
            >
              {label}
            </span>
            <span
              style={{
                fontFamily: '"IBM Plex Mono", monospace',
                fontSize: 12,
                fontWeight: 500,
                color: color ?? "#c9d1d9",
              }}
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* ── Period selector ── */}
      <div
        style={{
          display: "flex",
          gap: 2,
          padding: "0 16px 6px",
          flexShrink: 0,
        }}
      >
        {PERIODS.map(({ key, label }) => (
          <button
            key={key}
            data-period={key}
            onClick={() => setPeriod(key)}
            style={{
              background: period === key ? "#209dd7" : "transparent",
              border: `1px solid ${period === key ? "#209dd7" : "#30363d"}`,
              color: period === key ? "#0d1117" : "#8b949e",
              cursor: "pointer",
              padding: "2px 10px",
              borderRadius: 2,
              fontWeight: 600,
              fontSize: 10,
              letterSpacing: "0.06em",
              fontFamily: '"IBM Plex Mono", monospace',
              transition: "all 0.15s",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Chart ── */}
      <div style={{ flex: 1, minHeight: 0, minWidth: 0 }}>
        {loading ? (
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
            LOADING…
          </div>
        ) : chartData.length < 2 ? (
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
            {period === "1d" ? "STREAMING PRICES…" : "NO DATA"}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
              <XAxis
                dataKey="time"
                tick={{ fill: "#8b949e", fontSize: 9, fontFamily: '"IBM Plex Mono", monospace' }}
                tickLine={false}
                axisLine={{ stroke: "#30363d" }}
                interval="preserveStartEnd"
                minTickGap={40}
              />
              <YAxis
                domain={[minP - pad, maxP + pad]}
                tick={{ fill: "#8b949e", fontSize: 9, fontFamily: '"IBM Plex Mono", monospace' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) =>
                  `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`
                }
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
