"use client";
import { useState, useEffect } from "react";
import { api, formatInr, type PriceUpdate, ApiError } from "@/lib/api";

interface TradeBarProps {
  priceCache: Record<string, PriceUpdate>;
  selectedTicker: string | null;
  onTradeComplete: () => void;
}

export default function TradeBar({ priceCache, selectedTicker, onTradeComplete }: TradeBarProps) {
  const [ticker, setTicker] = useState(selectedTicker ?? "");
  const [quantity, setQuantity] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Sync ticker input when selection changes from watchlist click
  useEffect(() => {
    if (selectedTicker) setTicker(selectedTicker);
  }, [selectedTicker]);

  const activeTicker = ticker.trim().toUpperCase() || selectedTicker || "";
  const pd = activeTicker ? priceCache[activeTicker] : null;
  const qty = parseFloat(quantity);
  const estimatedCost = pd && !isNaN(qty) && qty > 0 ? pd.price * qty : null;

  const executeTrade = async (side: "buy" | "sell") => {
    if (!activeTicker || isNaN(qty) || qty <= 0) {
      setStatus("Enter a valid ticker and quantity");
      return;
    }
    setLoading(true);
    setStatus(null);
    try {
      const result = await api.trade(activeTicker, side, qty);
      setStatus(
        `${side === "buy" ? "Bought" : "Sold"} ${qty} ${activeTicker} @ ${formatInr(result.price)}`
      );
      setQuantity("");
      onTradeComplete();
    } catch (err) {
      setStatus(`Error: ${err instanceof ApiError ? err.detail : "Trade failed"}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 12px",
        borderTop: "1px solid #30363d",
        background: "#161b22",
        flexShrink: 0,
        flexWrap: "wrap",
      }}
    >
      <span
        style={{
          color: "#ecad0a",
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          fontFamily: '"IBM Plex Mono", monospace',
          whiteSpace: "nowrap",
        }}
      >
        TRADE
      </span>

      <input
        className="input-base"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        placeholder={selectedTicker ?? "TICKER"}
        style={{
          width: 90,
          padding: "4px 8px",
          fontSize: 12,
          letterSpacing: "0.06em",
          borderRadius: 2,
          fontWeight: 500,
        }}
      />

      <input
        className="input-base"
        type="number"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        placeholder="QTY"
        min={0}
        style={{
          width: 70,
          padding: "4px 8px",
          fontSize: 12,
          borderRadius: 2,
        }}
      />

      {estimatedCost !== null && (
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: 11,
            color: "#8b949e",
            whiteSpace: "nowrap",
          }}
        >
          ≈ {formatInr(estimatedCost)}
        </span>
      )}

      <button
        disabled={loading}
        onClick={() => executeTrade("buy")}
        style={{
          background: loading ? "#1a4053" : "#209dd7",
          border: "none",
          color: "#0d1117",
          cursor: loading ? "not-allowed" : "pointer",
          padding: "5px 16px",
          borderRadius: 2,
          fontWeight: 600,
          fontSize: 11,
          letterSpacing: "0.06em",
          fontFamily: '"IBM Plex Sans", sans-serif',
          textTransform: "uppercase",
        }}
      >
        {loading ? "…" : "BUY"}
      </button>

      <button
        disabled={loading}
        onClick={() => executeTrade("sell")}
        style={{
          background: loading ? "#2a1a35" : "#753991",
          border: "none",
          color: "#fff",
          cursor: loading ? "not-allowed" : "pointer",
          padding: "5px 16px",
          borderRadius: 2,
          fontWeight: 600,
          fontSize: 11,
          letterSpacing: "0.06em",
          fontFamily: '"IBM Plex Sans", sans-serif',
          textTransform: "uppercase",
        }}
      >
        {loading ? "…" : "SELL"}
      </button>

      {status && (
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontSize: 11,
            color: status.startsWith("Error") || status === "Trade failed" ? "#f85149" : "#3fb950",
            flex: 1,
          }}
        >
          {status}
        </span>
      )}
    </div>
  );
}
