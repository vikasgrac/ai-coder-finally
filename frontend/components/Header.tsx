"use client";
import { formatInr } from "@/lib/api";
import type { ConnectionStatus } from "@/lib/sse";

interface HeaderProps {
  totalValue: number;
  cash: number;
  status: ConnectionStatus;
}

const statusColor: Record<ConnectionStatus, string> = {
  connected: "#3fb950",
  reconnecting: "#d29922",
  disconnected: "#f85149",
};

const statusLabel: Record<ConnectionStatus, string> = {
  connected: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Offline",
};

export default function Header({ totalValue, cash, status }: HeaderProps) {
  return (
    <header
      style={{
        background: "#161b22",
        borderBottom: "1px solid #30363d",
        padding: "0 16px",
        height: 40,
        display: "flex",
        alignItems: "center",
        gap: 24,
        flexShrink: 0,
        userSelect: "none",
      }}
    >
      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            color: "#ecad0a",
            fontFamily: '"IBM Plex Mono", monospace',
            fontWeight: 600,
            fontSize: 14,
            letterSpacing: "0.05em",
          }}
        >
          FIN
        </span>
        <span
          style={{
            color: "#c9d1d9",
            fontFamily: '"IBM Plex Mono", monospace',
            fontWeight: 400,
            fontSize: 14,
            letterSpacing: "0.05em",
          }}
        >
          ALLY
        </span>
      </div>

      <div style={{ width: 1, height: 20, background: "#30363d" }} />

      {/* Portfolio value */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ color: "#8b949e", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Portfolio
        </span>
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontWeight: 600,
            fontSize: 14,
            color: "#c9d1d9",
          }}
        >
          {formatInr(totalValue)}
        </span>
      </div>

      <div style={{ width: 1, height: 20, background: "#30363d" }} />

      {/* Cash */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ color: "#8b949e", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Cash
        </span>
        <span
          style={{
            fontFamily: '"IBM Plex Mono", monospace',
            fontWeight: 400,
            fontSize: 13,
            color: "#ecad0a",
          }}
        >
          {formatInr(cash)}
        </span>
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Connection indicator */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          className={status === "connected" ? "pulse" : ""}
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: statusColor[status],
            display: "inline-block",
          }}
        />
        <span style={{ color: "#8b949e", fontSize: 11, letterSpacing: "0.05em" }}>
          {statusLabel[status]}
        </span>
      </div>
    </header>
  );
}
