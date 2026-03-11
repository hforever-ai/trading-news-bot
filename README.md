# 📰 Trading News Bot

A Telegram bot that monitors 16+ financial news sources and pushes real-time alerts for US and Indian markets.

## Features

- **16 RSS Feeds** — CNBC, MarketWatch, Nasdaq, Seeking Alpha, TheStreet, Motley Fool, Investing.com, Fed Reserve, ET Markets, Moneycontrol, Business Standard, Hindu BizLine, Livemint + Benzinga Pro API
- **Smart Keyword Filtering** — 60+ keywords covering US markets, Indian markets, macro, and corporate activity
- **Persistent Dedup** — Seen headlines saved to disk, so restarts don't re-send old news
- **FII/DII Daily Report** — Institutional investor data from NSE at 4:00 PM IST
- **Daily Health Check** — Reports which feeds are alive vs down at 8:00 AM IST
- **Rate-limit Handling** — Respects Telegram API limits with backoff

## Setup

### 1. Environment Variables

Set these on your host (recommended) or edit the fallback values in `main.py`:

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Your Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT` | Your chat ID (use [@userinfobot](https://t.me/userinfobot) to find it) |
| `BENZINGA_KEY` | Benzinga Pro API key (optional) |

### 2. Install & Run Locally

```bash
pip install -r requirements.txt
python main.py
```

### 3. Deploy to Heroku / Railway

The included `Procfile` works with Heroku:

```bash
heroku create my-news-bot
heroku config:set TELEGRAM_TOKEN=your_token
heroku config:set TELEGRAM_CHAT=your_chat_id
heroku config:set BENZINGA_KEY=your_key
git push heroku main
heroku ps:scale worker=1
```

## How It Works

1. Every **60 seconds**, fetches the latest headlines from all RSS feeds
2. Filters against **60+ keywords** for trading relevance
3. Deduplicates using MD5 hashes stored in `seen_hashes.json`
4. Sends matching headlines to your Telegram chat
5. At **4:00 PM IST**, posts FII/DII institutional data from NSE
6. At **8:00 AM IST**, posts a feed health report

## Adding/Removing Feeds

Edit the `FEEDS` dictionary in `main.py`:

```python
FEEDS = {
    'Source Name': 'https://example.com/rss/feed.xml',
    ...
}
```

## Adding Keywords

Edit the `KEYWORDS` list in `main.py`. Keywords are matched case-insensitively against headline titles.
