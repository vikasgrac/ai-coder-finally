# Massive API Reference

Massive (at `https://massive.com`, formerly Polygon.io) provides real-time and end-of-day US equity data. This document covers the endpoints used by FinAlly for price polling and historical OHLCV retrieval.

---

## Authentication

All requests require an API key passed as a query parameter:

```
?apiKey=YOUR_MASSIVE_API_KEY
```

Base URL: `https://api.polygon.io` (still active and used by the Massive SDK/clients)

```python
import os
API_KEY = os.environ["MASSIVE_API_KEY"]
BASE_URL = "https://api.polygon.io"
```

---

## Plan Tiers

| Plan | Latency | History | Notes |
|---|---|---|---|
| Free | End-of-day only | 2 years | No real-time |
| Developer | 15-min delayed | 2 years | Good for dev/testing |
| Starter | 15-min delayed | 5 years | REST only |
| Advanced | Real-time | Full | WebSocket access |
| Business | Real-time | Full | Fair market value, unlimited calls |

For FinAlly, the **Developer** plan is sufficient for development (15-min delay). For a live demo, **Advanced** is needed.

---

## REST Endpoints

### 1. Multi-Ticker Snapshot (Primary polling endpoint)

Fetches the latest data for multiple tickers in a single request — the most efficient endpoint for a watchlist.

```
GET /v2/snapshot/locale/us/markets/stocks/tickers
```

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tickers` | string | No | Comma-separated ticker list. Omit for all tickers. |
| `include_otc` | boolean | No | Include OTC securities (default: false) |
| `apiKey` | string | Yes | Your API key |

**Example request:**

```python
import httpx

async def get_snapshots(tickers: list[str]) -> dict:
    url = f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers"
    params = {
        "tickers": ",".join(tickers),
        "apiKey": API_KEY,
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()
```

**Example response:**

```json
{
  "status": "OK",
  "count": 2,
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 1.23,
      "todaysChangePerc": 0.82,
      "updated": 1617901342000,
      "day": {
        "o": 149.50,
        "h": 151.20,
        "l": 148.80,
        "c": 150.75,
        "v": 72456789,
        "vw": 150.12
      },
      "min": {
        "o": 150.60,
        "h": 150.80,
        "l": 150.55,
        "c": 150.75,
        "v": 123456,
        "vw": 150.68
      },
      "prevDay": {
        "o": 148.00,
        "h": 149.90,
        "l": 147.50,
        "c": 149.52,
        "v": 65432100,
        "vw": 148.85
      },
      "lastTrade": {
        "p": 150.75,
        "s": 100,
        "t": 1617901342969834000
      },
      "lastQuote": {
        "P": 150.76,
        "S": 2,
        "p": 150.74,
        "s": 5,
        "t": 1617901342970000000
      }
    }
  ]
}
```

**Key fields to extract:**

- `lastTrade.p` — most recent trade price (real-time or 15-min delayed)
- `todaysChangePerc` — daily percentage change
- `day.v` — today's volume
- `min` — most recent minute bar (useful for sparklines)

---

### 2. Last Trade (Single Ticker)

Returns the most recent trade for one ticker.

```
GET /v2/last/trade/{stocksTicker}
```

**Example request:**

```python
async def get_last_trade(ticker: str) -> dict:
    url = f"{BASE_URL}/v2/last/trade/{ticker}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params={"apiKey": API_KEY})
        r.raise_for_status()
        data = r.json()
        return {
            "ticker": ticker,
            "price": data["results"]["p"],
            "size": data["results"]["s"],
            "timestamp_ns": data["results"]["t"],
        }
```

**Example response:**

```json
{
  "request_id": "f05562305bd26ced64b98ed68b3c5d96",
  "status": "OK",
  "results": {
    "T": "AAPL",
    "p": 129.8473,
    "s": 25,
    "t": 1617901342969834000,
    "x": 4,
    "c": [37],
    "i": "118749",
    "q": 3135876
  }
}
```

**Key fields:**
- `results.p` — trade price
- `results.s` — trade size (shares)
- `results.t` — SIP timestamp in nanoseconds (divide by 1e6 for milliseconds)

---

### 3. Previous Day Close

Returns the OHLCV bar for the previous trading day.

```
GET /v2/aggs/ticker/{stocksTicker}/prev
```

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `adjusted` | boolean | true | Split-adjusted prices |
| `apiKey` | string | — | Required |

**Example request:**

```python
async def get_previous_close(ticker: str) -> dict:
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/prev"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params={"adjusted": "true", "apiKey": API_KEY})
        r.raise_for_status()
        data = r.json()
        bar = data["results"][0]
        return {
            "ticker": ticker,
            "open": bar["o"],
            "high": bar["h"],
            "low": bar["l"],
            "close": bar["c"],
            "volume": bar["v"],
            "vwap": bar["vw"],
            "timestamp_ms": bar["t"],
        }
```

**Example response:**

```json
{
  "ticker": "AAPL",
  "adjusted": true,
  "status": "OK",
  "resultsCount": 1,
  "results": [{
    "o": 115.55,
    "h": 117.59,
    "l": 114.13,
    "c": 115.97,
    "v": 131704427,
    "vw": 116.3058,
    "t": 1605042000000
  }]
}
```

---

### 4. Historical Aggregates (OHLCV Bars)

Returns OHLCV bars over a date range at any timespan.

```
GET /v2/aggs/ticker/{stocksTicker}/range/{multiplier}/{timespan}/{from}/{to}
```

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `stocksTicker` | string | Ticker symbol (case-sensitive) |
| `multiplier` | integer | Number of timespan units per bar (e.g., `1`) |
| `timespan` | string | `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year` |
| `from` | string | Start date `YYYY-MM-DD` or Unix ms timestamp |
| `to` | string | End date `YYYY-MM-DD` or Unix ms timestamp |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `adjusted` | boolean | true | Split-adjusted |
| `sort` | string | `asc` | Sort order: `asc` or `desc` |
| `limit` | integer | 5000 | Max 50000 |
| `apiKey` | string | — | Required |

**Example request — 30 days of daily bars:**

```python
from datetime import date, timedelta

async def get_daily_bars(ticker: str, days: int = 30) -> list[dict]:
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=days)).isoformat()
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": API_KEY,
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        return [
            {
                "timestamp_ms": bar["t"],
                "open": bar["o"],
                "high": bar["h"],
                "low": bar["l"],
                "close": bar["c"],
                "volume": bar["v"],
                "vwap": bar.get("vw"),
            }
            for bar in data.get("results", [])
        ]
```

**Example response:**

```json
{
  "ticker": "AAPL",
  "adjusted": true,
  "status": "OK",
  "resultsCount": 2,
  "results": [
    {"o": 74.06, "h": 75.15, "l": 73.80, "c": 75.09, "v": 135647456, "vw": 74.61, "t": 1577941200000},
    {"o": 74.29, "h": 75.15, "l": 74.13, "c": 74.36, "v": 146535512, "vw": 74.70, "t": 1578027600000}
  ]
}
```

**For intraday sparklines (1-minute bars today):**

```python
async def get_intraday_bars(ticker: str) -> list[dict]:
    today = date.today().isoformat()
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/minute/{today}/{today}"
    # ... same pattern as above
```

---

## WebSocket Streams (Real-time, Advanced/Business plans)

### Connection

```
WSS wss://socket.polygon.io/stocks
```

Authentication is done via a message after connecting:

```python
import asyncio
import websockets
import json

async def stream_trades(tickers: list[str]):
    uri = "wss://socket.polygon.io/stocks"
    async with websockets.connect(uri) as ws:
        # Authenticate
        await ws.send(json.dumps({"action": "auth", "params": API_KEY}))
        auth_resp = json.loads(await ws.recv())
        print(auth_resp)  # [{"ev":"status","status":"auth_success"}]

        # Subscribe to trade events
        ticker_param = ",".join(f"T.{t}" for t in tickers)
        await ws.send(json.dumps({"action": "subscribe", "params": ticker_param}))

        async for message in ws:
            events = json.loads(message)
            for event in events:
                if event["ev"] == "T":
                    print(f"{event['sym']}: ${event['p']} x {event['s']}")
```

### Trade Events (`T`)

```
WS /stocks/T
```

Subscribe pattern: `T.AAPL`, `T.MSFT`, or `T.*` for all tickers.

**Message fields:**

| Field | Description |
|---|---|
| `ev` | Event type: `"T"` |
| `sym` | Ticker symbol |
| `p` | Trade price |
| `s` | Trade size (shares) |
| `t` | SIP timestamp (Unix milliseconds) |
| `c` | Condition codes array |
| `x` | Exchange ID |

**Example event:**

```json
{
  "ev": "T",
  "sym": "MSFT",
  "p": 114.125,
  "s": 100,
  "c": [0, 12],
  "t": 1536036818784,
  "x": 4
}
```

### Second Aggregates (`A`)

```
WS /stocks/A
```

Subscribe pattern: `A.AAPL` or `A.*`. Fires every second with OHLCV for that window.

**Message fields:**

| Field | Description |
|---|---|
| `ev` | Event type: `"A"` |
| `sym` | Ticker symbol |
| `o`, `h`, `l`, `c` | Open/high/low/close for the second |
| `v` | Volume this second |
| `av` | Accumulated daily volume |
| `vw` | VWAP for the second |
| `s`, `e` | Start and end timestamps (Unix ms) |

**Example event:**

```json
{
  "ev": "A",
  "sym": "SPCE",
  "v": 200,
  "av": 4112966,
  "o": 25.39,
  "c": 25.39,
  "h": 25.39,
  "l": 25.39,
  "s": 1610144868000,
  "e": 1610144869000
}
```

---

## Rate Limits

| Plan | Requests/minute | Notes |
|---|---|---|
| Free | Unlimited calls | End-of-day data only |
| Developer | Unlimited | 15-min delayed |
| Starter+ | Unlimited | Per fair-use policy |

The snapshot endpoint is highly efficient — one call fetches all tickers simultaneously, so rate limits are rarely a concern for a watchlist of 10–50 tickers.

---

## Error Handling

All endpoints return a `status` field. On error, `status` is `"ERROR"` and `error` contains the message:

```json
{
  "status": "ERROR",
  "error": "You exceeded your rate limit. Please review our rate limit guide."
}
```

```python
def check_response(data: dict) -> None:
    if data.get("status") not in ("OK", "DELAYED"):
        raise RuntimeError(f"Massive API error: {data.get('error', data)}")
```

Note: `status: "DELAYED"` is normal for Developer/Starter plans — prices are 15 minutes behind but the response is otherwise identical.
