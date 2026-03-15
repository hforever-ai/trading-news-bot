# Trading News Bot v2 — API-First Architecture

Real-time market news delivered to your Telegram. Uses **APIs, not RSS feeds**.

## Sources

| Source | Free Tier | Poll Rate | What It Covers |
|--------|-----------|-----------|----------------|
| **Finnhub** | 60 calls/min | Every 30s | General market news + ticker-specific |
| **NewsAPI** | 100 calls/day | Every 5 min | Broad news search across thousands of sources |
| **Polygon.io** | 5 calls/min | Every 2 min | Ticker-specific news, SEC filings |

**You need at least 1 API key.** More sources = better coverage.

## What's Fixed vs v1

- **No more spam on boot** — Cold start silently indexes existing headlines, only sends NEW ones
- **No RSS** — Pure API-based, faster and more reliable
- **Fuzzy dedup** — Similar headlines from different sources won't double-send (82% similarity threshold)
- **Smart batching** — Tickers rotate across cycles to stay within free tier limits
- **Categorized news** — Headlines tagged with 🇺🇸 🇮🇳 💰 🟢 🔴 🌍 etc.
- **Persistent dedup** — Survives Railway restarts via file-based seen set
- **Proper scheduling** — Each source polls at its own optimal interval

## Setup

### 1. Get Free API Keys

- **Finnhub** (recommended): https://finnhub.io/register → free key, 60 calls/min
- **NewsAPI**: https://newsapi.org/register → free key, 100 calls/day
- **Polygon.io**: https://polygon.io/dashboard/signup → free key, 5 calls/min

### 2. Railway Env Vars

```
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT=your_chat_id
FINNHUB_KEY=your_finnhub_key
NEWSAPI_KEY=your_newsapi_key       # optional
POLYGON_KEY=your_polygon_key       # optional
```

### 3. Deploy

Push to GitHub → connect to Railway → set env vars → deploy.

Railway `Procfile` uses `worker` process (not `web`) so it stays alive.

## Customize

- **Add tickers**: Edit `US_TICKERS` and `INDIA_SYMBOLS` in `main.py`
- **Add keywords**: Edit `KEYWORDS` list
- **Change intervals**: Edit `FINNHUB_INTERVAL`, `NEWSAPI_INTERVAL`, `POLYGON_INTERVAL`
- **FII/DII time**: Adjust `FIIDII_HOUR_UTC` and `FIIDII_MINUTE_UTC`
