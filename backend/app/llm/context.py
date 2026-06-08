"""Build the system prompt and portfolio context injected before each LLM call."""

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant for an Indian stock market simulation.
You help users analyze their portfolio, suggest trades, and execute them on their behalf.

Rules:
- Always respond with valid JSON matching the schema: {message, trades, watchlist_changes}
- trades: array of {ticker, side (buy/sell), quantity}
- watchlist_changes: array of {ticker, action (add/remove)}
- Be concise and data-driven
- Execute trades when the user asks or agrees
- All prices are in INR (₹)
- Only suggest trades you can justify from the portfolio context
"""


def build_context_block(portfolio: dict) -> str:
    """Format the current portfolio state as a readable context block."""
    cash = portfolio.get("cash", 0)
    total = portfolio.get("total_value", 0)
    positions = portfolio.get("positions", [])
    watchlist = portfolio.get("watchlist", [])

    lines = [
        f"Cash: ₹{cash:,.2f}",
        f"Total Portfolio Value: ₹{total:,.2f}",
        "",
        "Positions:",
    ]
    if positions:
        for p in positions:
            pnl_sign = "+" if p.get("unrealized_pnl", 0) >= 0 else ""
            lines.append(
                f"  {p['ticker']}: {p['quantity']} shares @ avg ₹{p['avg_cost']:.2f}, "
                f"current ₹{p['current_price']:.2f}, "
                f"P&L {pnl_sign}₹{p['unrealized_pnl']:.2f} ({pnl_sign}{p['pct_change']:.1f}%)"
            )
    else:
        lines.append("  (none)")

    lines += ["", "Watchlist prices:"]
    if watchlist:
        for w in watchlist:
            price_str = f"₹{w['price']:.2f}" if w.get("price") else "N/A"
            lines.append(f"  {w['ticker']}: {price_str}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def build_messages(
    portfolio: dict,
    history: list[dict],
    user_message: str,
) -> list[dict]:
    """Construct the full messages list for the LLM call."""
    context = build_context_block(portfolio)
    system_with_context = f"{SYSTEM_PROMPT}\n\nCurrent Portfolio:\n{context}"

    messages = [{"role": "system", "content": system_with_context}]

    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages
