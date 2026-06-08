"use client";
import { useState, useEffect, useRef } from "react";
import { formatInr, type WatchlistItem, type PriceUpdate } from "@/lib/api";
import type { PriceHistory } from "@/lib/sse";

interface WatchlistPanelProps {
  items: WatchlistItem[];
  priceCache: Record<string, PriceUpdate>;
  priceHistory: Record<string, PriceHistory[]>;
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

function Sparkline({ history }: { history: PriceHistory[] }) {
  if (history.length < 2) {
    return <svg width={60} height={20} style={{ opacity: 0.2 }}><line x1={0} y1={10} x2={60} y2={10} stroke="#8b949e" strokeWidth={1} /></svg>;
  }

  const pts = history.slice(-20);
  const prices = pts.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;

  const points = pts
    .map((p, i) => {
      const x = (i / (pts.length - 1)) * 58 + 1;
      const y = 18 - ((p.price - min) / range) * 16 + 1;
      return `${x},${y}`;
    })
    .join(" ");

  const lastPrice = prices[prices.length - 1];
  const firstPrice = prices[0];
  const color = lastPrice >= firstPrice ? "#3fb950" : "#f85149";

  return (
    <svg width={60} height={20}>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.2}
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.8}
      />
    </svg>
  );
}

function PriceCell({ ticker, priceCache }: { ticker: string; priceCache: Record<string, PriceUpdate> }) {
  const pd = priceCache[ticker];
  const [flashClass, setFlashClass] = useState("");
  const prevPriceRef = useRef<number | null>(null);

  useEffect(() => {
    if (!pd) return;
    const prev = prevPriceRef.current;
    if (prev !== null && prev !== pd.price) {
      setFlashClass(pd.price > prev ? "price-flash-up" : "price-flash-down");
      const t = setTimeout(() => setFlashClass(""), 520);
      return () => clearTimeout(t);
    }
    prevPriceRef.current = pd.price;
  }, [pd?.price]);

  if (!pd) {
    return (
      <span style={{ color: "#8b949e", fontFamily: '"IBM Plex Mono", monospace', fontSize: 12 }}>
        —
      </span>
    );
  }

  const pctChange = pd.previous_price > 0
    ? ((pd.price - pd.previous_price) / pd.previous_price) * 100
    : 0;
  const isUp = pd.change_direction === "up";
  const isDown = pd.change_direction === "down";

  return (
    <span
      className={flashClass}
      style={{
        display: "inline-flex",
        flexDirection: "column",
        gap: 1,
      }}
    >
      <span
        style={{
          fontFamily: '"IBM Plex Mono", monospace',
          fontWeight: 500,
          fontSize: 12,
          color: isUp ? "#3fb950" : isDown ? "#f85149" : "#c9d1d9",
        }}
      >
        {formatInr(pd.price)}
      </span>
      <span
        style={{
          fontFamily: '"IBM Plex Mono", monospace',
          fontSize: 10,
          color: isUp ? "#3fb950" : isDown ? "#f85149" : "#8b949e",
        }}
      >
        {pctChange >= 0 ? "+" : ""}{pctChange.toFixed(2)}%
      </span>
    </span>
  );
}

export default function WatchlistPanel({
  items,
  priceCache,
  priceHistory,
  selectedTicker,
  onSelect,
  onAdd,
  onRemove,
}: WatchlistPanelProps) {
  const [addInput, setAddInput] = useState("");

  const handleAdd = () => {
    const t = addInput.trim().toUpperCase();
    if (t) {
      onAdd(t);
      setAddInput("");
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        background: "#161b22",
        borderRight: "1px solid #30363d",
        width: 220,
        flexShrink: 0,
        overflow: "hidden",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto auto",
          padding: "6px 10px",
          borderBottom: "1px solid #30363d",
          background: "#0d1117",
        }}
      >
        <span style={{ color: "#8b949e", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Symbol
        </span>
        <span style={{ color: "#8b949e", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Price
        </span>
        <span style={{ width: 60, marginLeft: 4 }} />
      </div>

      {/* Ticker list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {items.map((item) => {
          const isSelected = item.ticker === selectedTicker;
          return (
            <div
              key={item.ticker}
              className="hover-row"
              onClick={() => onSelect(item.ticker)}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto auto",
                alignItems: "center",
                padding: "5px 10px",
                borderBottom: "1px solid rgba(48,54,61,0.5)",
                cursor: "pointer",
                background: isSelected ? "rgba(32,157,215,0.08)" : undefined,
                borderLeft: isSelected ? "2px solid #209dd7" : "2px solid transparent",
                gap: 4,
              }}
            >
              {/* Ticker + sparkline */}
              <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span
                    style={{
                      fontFamily: '"IBM Plex Mono", monospace',
                      fontWeight: 500,
                      fontSize: 11,
                      color: isSelected ? "#209dd7" : "#c9d1d9",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {item.ticker}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); onRemove(item.ticker); }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "#30363d",
                      cursor: "pointer",
                      padding: 0,
                      fontSize: 10,
                      lineHeight: 1,
                      display: "flex",
                      alignItems: "center",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#f85149")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = "#30363d")}
                    title="Remove"
                  >
                    ✕
                  </button>
                </div>
                <Sparkline history={priceHistory[item.ticker] ?? []} />
              </div>

              {/* Price */}
              <PriceCell ticker={item.ticker} priceCache={priceCache} />
            </div>
          );
        })}
      </div>

      {/* Add ticker input */}
      <div
        style={{
          padding: "8px 10px",
          borderTop: "1px solid #30363d",
          display: "flex",
          gap: 6,
        }}
      >
        <input
          className="input-base"
          value={addInput}
          onChange={(e) => setAddInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="+ ADD TICKER"
          style={{
            flex: 1,
            padding: "4px 6px",
            fontSize: 11,
            letterSpacing: "0.06em",
            borderRadius: 2,
          }}
        />
        <button
          onClick={handleAdd}
          style={{
            background: "#209dd7",
            border: "none",
            color: "#0d1117",
            cursor: "pointer",
            padding: "4px 8px",
            borderRadius: 2,
            fontWeight: 600,
            fontSize: 11,
          }}
        >
          +
        </button>
      </div>
    </div>
  );
}
