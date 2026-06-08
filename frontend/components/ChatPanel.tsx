"use client";
import { useState, useRef, useEffect } from "react";
import { api, formatInr } from "@/lib/api";
import type { ChatResponse } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  actions?: ChatResponse["actions"];
}

export default function ChatPanel({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const resp = await api.chat(text);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: resp.message, actions: resp.actions },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, I couldn't connect to the AI backend." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div
      style={{
        width: open ? 280 : 32,
        flexShrink: 0,
        background: "#161b22",
        borderLeft: "1px solid #30363d",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.2s ease",
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Toggle tab */}
      <button
        onClick={onToggle}
        style={{
          position: "absolute",
          top: "50%",
          left: 0,
          transform: "translateY(-50%)",
          background: "#30363d",
          border: "none",
          color: "#8b949e",
          cursor: "pointer",
          width: 16,
          height: 48,
          borderRadius: "0 3px 3px 0",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 8,
          zIndex: 10,
          writingMode: "vertical-rl",
          padding: 0,
        }}
        title={open ? "Collapse AI panel" : "Expand AI panel"}
      >
        {open ? "›" : "‹"}
      </button>

      {open && (
        <>
          {/* Header */}
          <div
            style={{
              padding: "8px 12px 8px 20px",
              borderBottom: "1px solid #30363d",
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "#0d1117",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "#ecad0a",
                display: "inline-block",
              }}
            />
            <span
              style={{
                color: "#ecad0a",
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                fontFamily: '"IBM Plex Mono", monospace',
              }}
            >
              AI Assistant
            </span>
          </div>

          {/* Messages */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "8px 12px",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {messages.length === 0 && !loading && (
              <div
                style={{
                  color: "#8b949e",
                  fontSize: 11,
                  textAlign: "center",
                  padding: "24px 8px",
                  lineHeight: 1.6,
                }}
              >
                Ask me to analyze your portfolio, suggest trades, or buy/sell stocks.
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                  }}
                >
                  <div
                    style={{
                      maxWidth: "90%",
                      padding: "6px 10px",
                      borderRadius: msg.role === "user" ? "8px 8px 2px 8px" : "8px 8px 8px 2px",
                      background: msg.role === "user" ? "#1c4966" : "#1e2531",
                      color: "#c9d1d9",
                      fontSize: 12,
                      lineHeight: 1.5,
                      fontFamily: '"IBM Plex Sans", sans-serif',
                    }}
                  >
                    {msg.content}
                  </div>
                </div>

                {/* Action chips */}
                {msg.actions && (
                  <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {msg.actions.trades.filter((t) => !("error" in t) || !t.error).map((t, j) => (
                      <span
                        key={j}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          background: t.side === "buy" ? "rgba(32,157,215,0.15)" : "rgba(117,57,145,0.15)",
                          border: `1px solid ${t.side === "buy" ? "#209dd7" : "#753991"}`,
                          borderRadius: 2,
                          padding: "2px 6px",
                          fontSize: 10,
                          fontFamily: '"IBM Plex Mono", monospace',
                          color: t.side === "buy" ? "#209dd7" : "#c084fc",
                        }}
                      >
                        {t.side.toUpperCase()} {t.quantity} {t.ticker}
                        {t.price && <> @ {formatInr(t.price)}</>}
                      </span>
                    ))}
                    {msg.actions.trades.filter((t) => ("error" in t) && t.error).map((t, j) => (
                      <span
                        key={`err-${j}`}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          background: "rgba(248,81,73,0.1)",
                          border: "1px solid #f85149",
                          borderRadius: 2,
                          padding: "2px 6px",
                          fontSize: 10,
                          fontFamily: '"IBM Plex Mono", monospace',
                          color: "#f85149",
                        }}
                      >
                        ✕ {t.ticker}: {t.error}
                      </span>
                    ))}
                    {msg.actions.watchlist_changes.map((w, j) => (
                      <span
                        key={`wl-${j}`}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          background: "rgba(236,173,10,0.1)",
                          border: "1px solid #ecad0a",
                          borderRadius: 2,
                          padding: "2px 6px",
                          fontSize: 10,
                          fontFamily: '"IBM Plex Mono", monospace',
                          color: "#ecad0a",
                        }}
                      >
                        {w.action === "add" ? "+" : "−"} {w.ticker}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* Loading indicator */}
            {loading && (
              <div style={{ display: "flex", gap: 4, padding: "4px 0", alignItems: "center" }}>
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: "50%",
                      background: "#ecad0a",
                      animation: `pulse-dot 1.2s ease-in-out ${i * 0.2}s infinite`,
                    }}
                  />
                ))}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div
            style={{
              padding: "8px 12px",
              borderTop: "1px solid #30363d",
              display: "flex",
              gap: 6,
              alignItems: "flex-end",
            }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask FinAlly…"
              disabled={loading}
              rows={1}
              style={{
                flex: 1,
                resize: "none",
                background: "#0d1117",
                border: "1px solid #30363d",
                color: "#c9d1d9",
                padding: "6px 8px",
                fontSize: 12,
                borderRadius: 2,
                outline: "none",
                fontFamily: '"IBM Plex Sans", sans-serif',
                lineHeight: 1.4,
                maxHeight: 80,
                overflow: "auto",
              }}
              onFocus={(e) => (e.target.style.borderColor = "#209dd7")}
              onBlur={(e) => (e.target.style.borderColor = "#30363d")}
            />
            <button
              disabled={loading || !input.trim()}
              onClick={sendMessage}
              style={{
                background: loading || !input.trim() ? "#1a2030" : "#753991",
                border: "none",
                color: "#fff",
                cursor: loading || !input.trim() ? "not-allowed" : "pointer",
                padding: "6px 10px",
                borderRadius: 2,
                fontWeight: 600,
                fontSize: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                opacity: loading || !input.trim() ? 0.5 : 1,
              }}
              title="Send (Enter)"
            >
              ↑
            </button>
          </div>
        </>
      )}
    </div>
  );
}
