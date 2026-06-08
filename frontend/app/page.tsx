"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type Portfolio, type WatchlistItem } from "@/lib/api";
import { useSSEPrices } from "@/lib/sse";
import Header from "@/components/Header";
import WatchlistPanel from "@/components/WatchlistPanel";
import StockDetail from "@/components/StockDetail";
import PortfolioHeatmap from "@/components/PortfolioHeatmap";
import PnLChart from "@/components/PnLChart";
import PositionsTable from "@/components/PositionsTable";
import TradeBar from "@/components/TradeBar";
import ChatPanel from "@/components/ChatPanel";

const EMPTY_PORTFOLIO: Portfolio = { cash: 100000, positions: [], total_value: 100000 };

export default function Home() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio>(EMPTY_PORTFOLIO);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);

  const { priceCache, priceHistory, status } = useSSEPrices();

  const refreshPortfolio = useCallback(async () => {
    try {
      const p = await api.getPortfolio();
      setPortfolio(p);
    } catch {
      // keep stale
    }
  }, []);

  const refreshWatchlist = useCallback(async () => {
    try {
      const wl = await api.getWatchlist();
      setWatchlist(wl);
    } catch {
      // keep stale
    }
  }, []);

  // Initial load
  useEffect(() => {
    refreshWatchlist();
    refreshPortfolio();
  }, [refreshWatchlist, refreshPortfolio]);

  // Poll portfolio every 5 s
  useEffect(() => {
    const interval = setInterval(refreshPortfolio, 5000);
    return () => clearInterval(interval);
  }, [refreshPortfolio]);

  const handleAddTicker = async (ticker: string) => {
    try {
      await api.addTicker(ticker);
      await refreshWatchlist();
    } catch {
      // ignore 409 duplicates
    }
  };

  const handleRemoveTicker = async (ticker: string) => {
    try {
      await api.removeTicker(ticker);
      await refreshWatchlist();
      if (selectedTicker === ticker) setSelectedTicker(null);
    } catch {
      // ignore
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        background: "#0d1117",
      }}
    >
      {/* Header */}
      <Header
        totalValue={portfolio.total_value}
        cash={portfolio.cash}
        status={status}
      />

      {/* Main body */}
      <div style={{ flex: 1, display: "flex", minHeight: 0, overflow: "hidden" }}>
        {/* Watchlist */}
        <WatchlistPanel
          items={watchlist}
          priceCache={priceCache}
          priceHistory={priceHistory}
          selectedTicker={selectedTicker}
          onSelect={setSelectedTicker}
          onAdd={handleAddTicker}
          onRemove={handleRemoveTicker}
        />

        {/* Center column */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            overflow: "hidden",
          }}
        >
          {/* Top: main chart + portfolio heat / pnl */}
          <div
            style={{
              display: "flex",
              flex: "0 0 260px",
              borderBottom: "1px solid #30363d",
            }}
          >
            {/* Main chart */}
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                borderRight: "1px solid #30363d",
                overflow: "hidden",
                background: "#0d1117",
              }}
            >
              <StockDetail
                ticker={selectedTicker}
                priceHistory={priceHistory}
                priceCache={priceCache}
              />
            </div>

            {/* Portfolio heat + P&L */}
            <div
              style={{
                width: 340,
                display: "flex",
                flexDirection: "column",
                flexShrink: 0,
              }}
            >
              {/* Heatmap */}
              <div
                style={{
                  flex: 1,
                  borderBottom: "1px solid #30363d",
                  padding: 8,
                  background: "#0d1117",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    color: "#8b949e",
                    fontSize: 9,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                    marginBottom: 4,
                  }}
                >
                  Positions
                </div>
                <div style={{ height: "calc(100% - 18px)" }}>
                  <PortfolioHeatmap
                    positions={portfolio.positions}
                    onSelectTicker={setSelectedTicker}
                  />
                </div>
              </div>

              {/* P&L chart */}
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  background: "#0d1117",
                  overflow: "hidden",
                }}
              >
                <PnLChart totalValue={portfolio.total_value} />
              </div>
            </div>
          </div>

          {/* Positions table */}
          <div
            style={{
              flex: 1,
              minHeight: 0,
              overflow: "hidden",
              borderBottom: "1px solid #30363d",
            }}
          >
            <div
              style={{
                padding: "4px 10px",
                background: "#0d1117",
                borderBottom: "1px solid #30363d",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                style={{
                  color: "#8b949e",
                  fontSize: 9,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                }}
              >
                Positions
              </span>
              <span
                style={{
                  background: "#30363d",
                  color: "#8b949e",
                  fontSize: 9,
                  borderRadius: 10,
                  padding: "1px 6px",
                  fontFamily: '"IBM Plex Mono", monospace',
                }}
              >
                {portfolio.positions.length}
              </span>
            </div>
            <div style={{ height: "calc(100% - 28px)", overflow: "auto" }}>
              <PositionsTable
                positions={portfolio.positions}
                onSelectTicker={setSelectedTicker}
              />
            </div>
          </div>

          {/* Trade bar */}
          <TradeBar
            priceCache={priceCache}
            selectedTicker={selectedTicker}
            onTradeComplete={() => {
              refreshPortfolio();
              refreshWatchlist();
            }}
          />
        </div>

        {/* Chat panel */}
        <ChatPanel open={chatOpen} onToggle={() => setChatOpen((o) => !o)} />
      </div>
    </div>
  );
}
