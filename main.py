"""
Trading News Bot v2 — API-First Architecture
=============================================
Sources: Finnhub (primary), NewsAPI (secondary), Polygon.io (tertiary)
No RSS feeds. Real-time API polling with smart dedup.

Deploy on Railway with these env vars:
  TELEGRAM_TOKEN, TELEGRAM_CHAT,
  FINNHUB_KEY, NEWSAPI_KEY, POLYGON_KEY  (at least one required)
"""

import requests
import time
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

# ─── CONFIG ─────────────────────────────────────────────────────────
TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
CHAT  = os.environ.get('TELEGRAM_CHAT', '')

# API Keys — bot works with ANY combination (at least 1 needed)
FINNHUB_KEY  = os.environ.get('FINNHUB_KEY', '')     # Free: 60 calls/min
NEWSAPI_KEY  = os.environ.get('NEWSAPI_KEY', '')      # Free: 100 calls/day
POLYGON_KEY  = os.environ.get('POLYGON_KEY', '')      # Free: 5 calls/min

# ─── TIMING (seconds) ──────────────────────────────────────────────
FINNHUB_INTERVAL  = 30     # Poll Finnhub every 30s
NEWSAPI_INTERVAL  = 300    # Poll NewsAPI every 5 min (save daily quota)
POLYGON_INTERVAL  = 120    # Poll Polygon every 2 min
FIIDII_HOUR_UTC   = 10     # 4:00 PM IST = 10:30 UTC
FIIDII_MINUTE_UTC = 30

# ─── KEYWORDS (US + Indian Markets) ────────────────────────────────
KEYWORDS = [
    # General market
    'stock', 'market', 'earnings', 'trading', 'investor', 'wall street',
    'bull', 'bear', 'rally', 'plunge', 'surge', 'crash', 'selloff',
    'sell-off', 'downturn', 'rebound', 'correction', 'volatility',
    # US specific
    'fed', 'federal reserve', 'fomc', 'nasdaq', 'dow jones', 's&p 500',
    's&p500', 'nyse', 'treasury', 'rate hike', 'rate cut', 'interest rate',
    'inflation', 'cpi', 'ppi', 'jobs report', 'nonfarm', 'gdp',
    'recession', 'stimulus', 'debt ceiling',
    # Indian specific
    'nifty', 'sensex', 'bse', 'nse', 'banknifty', 'bank nifty',
    'rbi', 'sebi', 'fii', 'dii', 'rupee', 'nifty50',
    'adani', 'reliance', 'tata', 'infosys', 'hdfc', 'icici',
    # Corporate / deal activity
    'ipo', 'merger', 'acquisition', 'takeover', 'buyout', 'spinoff',
    'bankruptcy', 'dividend', 'buyback', 'stock split',
    'sec filing', 'quarterly results',
    # Macro / trade
    'tariff', 'trade war', 'sanctions', 'oil price', 'crude oil',
    'gold price', 'bond yield', 'dollar index',
]

# Tickers to track on Finnhub (batched to stay within rate limits)
US_TICKERS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'SPY', 'QQQ']
INDIA_SYMBOLS = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'ADANIENT', 'TATAMOTORS', 'SBIN']

# ─── DEDUP ENGINE ──────────────────────────────────────────────────
SEEN_FILE   = 'seen_hashes.json'
MAX_SEEN    = 8000
TITLE_CACHE = []           # recent titles for fuzzy matching
MAX_TITLE_CACHE = 500
SIMILARITY_THRESHOLD = 0.82  # titles >82% similar = duplicate

def load_seen() -> set:
    try:
        with open(SEEN_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('hashes', []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen(seen_set: set):
    hashes = list(seen_set)
    if len(hashes) > MAX_SEEN:
        hashes = hashes[-MAX_SEEN:]
    try:
        with open(SEEN_FILE, 'w') as f:
            json.dump({'hashes': hashes, 'updated': datetime.now().isoformat()}, f)
    except Exception as e:
        log(f'Save seen err: {e}')

seen = load_seen()

def make_hash(title: str, url: str = '') -> str:
    """Create dedup hash from normalized title + url."""
    clean = re.sub(r'\s+', ' ', title.strip().lower())
    return hashlib.md5((clean + url).encode()).hexdigest()

def is_fuzzy_duplicate(title: str) -> bool:
    """Check if title is too similar to a recently sent headline."""
    clean = re.sub(r'\s+', ' ', title.strip().lower())
    for cached in TITLE_CACHE[-MAX_TITLE_CACHE:]:
        if SequenceMatcher(None, clean, cached).ratio() > SIMILARITY_THRESHOLD:
            return True
    return False

def mark_sent(title: str, h: str):
    """Mark a headline as sent (hash + title cache)."""
    seen.add(h)
    clean = re.sub(r'\s+', ' ', title.strip().lower())
    TITLE_CACHE.append(clean)
    if len(TITLE_CACHE) > MAX_TITLE_CACHE:
        TITLE_CACHE.pop(0)

# ─── KEYWORD MATCHER ───────────────────────────────────────────────
def matches_keywords(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in KEYWORDS)

def categorize(title: str) -> str:
    """Return an emoji category tag for the headline."""
    t = title.lower()
    if any(k in t for k in ['nifty', 'sensex', 'bse', 'nse', 'rbi', 'sebi', 'fii', 'dii', 'rupee',
                             'adani', 'reliance', 'tata', 'infosys', 'hdfc', 'icici']):
        return '🇮🇳'
    if any(k in t for k in ['fed', 'fomc', 'nasdaq', 'dow', 's&p', 'nyse', 'treasury', 'wall street']):
        return '🇺🇸'
    if any(k in t for k in ['earnings', 'quarterly results', 'revenue', 'profit', 'eps']):
        return '💰'
    if any(k in t for k in ['ipo', 'merger', 'acquisition', 'takeover', 'buyout']):
        return '🤝'
    if any(k in t for k in ['crash', 'plunge', 'selloff', 'sell-off', 'bear']):
        return '🔴'
    if any(k in t for k in ['rally', 'surge', 'bull', 'rebound']):
        return '🟢'
    if any(k in t for k in ['oil', 'crude', 'gold', 'bond', 'dollar', 'tariff', 'inflation', 'cpi']):
        return '🌍'
    return '📰'

# ─── LOGGING ───────────────────────────────────────────────────────
def log(msg: str):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}', flush=True)

# ─── TELEGRAM ──────────────────────────────────────────────────────
def tg(msg: str):
    if not TOKEN or not CHAT:
        log(f'TG not configured. Message: {msg[:80]}...')
        return
    for attempt in range(3):
        try:
            r = requests.post(
                f'https://api.telegram.org/bot{TOKEN}/sendMessage',
                json={
                    'chat_id': CHAT,
                    'text': msg,
                    'disable_web_page_preview': True,
                    'parse_mode': 'HTML',
                },
                timeout=15,
            )
            if r.status_code == 429:
                wait = r.json().get('parameters', {}).get('retry_after', 5)
                log(f'TG rate limited, waiting {wait}s')
                time.sleep(wait)
                continue
            if r.status_code == 200:
                return
            log(f'TG HTTP {r.status_code}: {r.text[:100]}')
            return
        except Exception as e:
            log(f'TG err (attempt {attempt+1}): {e}')
            time.sleep(2)

def send_headline(source: str, title: str, url: str = '', summary: str = ''):
    """Format and send a single headline to Telegram."""
    cat = categorize(title)
    parts = [f'{cat} <b>[{source}]</b>', title]
    if summary:
        parts.append(f'<i>{summary[:200]}</i>')
    if url:
        parts.append(url)
    tg('\n'.join(parts))
    time.sleep(0.4)  # avoid TG flood

# ═══════════════════════════════════════════════════════════════════
#  SOURCE 1: FINNHUB  (Primary — fast, high rate limit)
# ═══════════════════════════════════════════════════════════════════

def fetch_finnhub_general():
    """Fetch general market news from Finnhub."""
    if not FINNHUB_KEY:
        return 0
    count = 0
    try:
        r = requests.get(
            'https://finnhub.io/api/v1/news',
            params={'category': 'general', 'token': FINNHUB_KEY},
            timeout=15,
        )
        if r.status_code != 200:
            log(f'Finnhub general HTTP {r.status_code}')
            return 0

        articles = r.json()
        for art in articles[:20]:
            title   = art.get('headline', '').strip()
            url     = art.get('url', '')
            summary = art.get('summary', '')[:200]
            if not title:
                continue

            h = make_hash(title, url)
            if h in seen:
                continue
            if is_fuzzy_duplicate(title):
                seen.add(h)
                continue

            if matches_keywords(title):
                mark_sent(title, h)
                send_headline('Finnhub', title, url, summary)
                count += 1
            else:
                seen.add(h)  # mark seen even if not matching

    except Exception as e:
        log(f'Finnhub general err: {e}')
    return count

def fetch_finnhub_ticker(symbols: list, batch_label: str = ''):
    """Fetch company-specific news from Finnhub for given symbols."""
    if not FINNHUB_KEY:
        return 0
    count = 0
    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')

    for sym in symbols:
        try:
            r = requests.get(
                'https://finnhub.io/api/v1/company-news',
                params={
                    'symbol': sym,
                    'from': week_ago,
                    'to': today,
                    'token': FINNHUB_KEY,
                },
                timeout=15,
            )
            if r.status_code != 200:
                continue

            articles = r.json()
            for art in articles[:5]:
                title   = art.get('headline', '').strip()
                url     = art.get('url', '')
                summary = art.get('summary', '')[:200]
                if not title:
                    continue

                h = make_hash(title, url)
                if h in seen or is_fuzzy_duplicate(title):
                    seen.add(h)
                    continue

                mark_sent(title, h)
                send_headline(f'Finnhub/{sym}', title, url, summary)
                count += 1

            time.sleep(0.3)  # pace API calls
        except Exception as e:
            log(f'Finnhub ticker {sym} err: {e}')
    return count

# Batch tickers across cycles to stay within Finnhub free tier
_finnhub_ticker_cycle = 0

def fetch_finnhub():
    """Run Finnhub: general news every cycle, tickers batched across 4 cycles."""
    global _finnhub_ticker_cycle
    total = fetch_finnhub_general()

    # Rotate through ticker batches: US batch 1, US batch 2, India batch 1, India batch 2
    batches = [
        (US_TICKERS[:5],  'US-1'),
        (US_TICKERS[5:],  'US-2'),
        (INDIA_SYMBOLS[:4], 'IN-1'),
        (INDIA_SYMBOLS[4:], 'IN-2'),
    ]
    idx = _finnhub_ticker_cycle % len(batches)
    symbols, label = batches[idx]
    total += fetch_finnhub_ticker(symbols, label)
    _finnhub_ticker_cycle += 1

    if total:
        log(f'Finnhub: sent {total} headlines (ticker batch {label})')
    return total


# ═══════════════════════════════════════════════════════════════════
#  SOURCE 2: NEWSAPI  (Secondary — broad coverage, lower quota)
# ═══════════════════════════════════════════════════════════════════

# Rotate queries to maximize coverage within 100/day free limit
NEWSAPI_QUERIES = [
    'stock market today',
    'federal reserve interest rate',
    'nifty sensex india market',
    'earnings report quarterly results',
    'IPO merger acquisition',
    'oil gold bond yield',
    'crypto bitcoin ethereum',
    'tariff trade war sanctions',
]
_newsapi_query_idx = 0

def fetch_newsapi():
    """Fetch headlines from NewsAPI (rotates queries to save quota)."""
    global _newsapi_query_idx
    if not NEWSAPI_KEY:
        return 0
    count = 0
    query = NEWSAPI_QUERIES[_newsapi_query_idx % len(NEWSAPI_QUERIES)]
    _newsapi_query_idx += 1

    try:
        r = requests.get(
            'https://newsapi.org/v2/everything',
            params={
                'q': query,
                'sortBy': 'publishedAt',
                'language': 'en',
                'pageSize': 10,
                'apiKey': NEWSAPI_KEY,
            },
            timeout=15,
        )
        if r.status_code != 200:
            log(f'NewsAPI HTTP {r.status_code}: {r.text[:100]}')
            return 0

        data = r.json()
        for art in data.get('articles', []):
            title = (art.get('title') or '').strip()
            url   = art.get('url', '')
            desc  = (art.get('description') or '')[:200]
            src   = art.get('source', {}).get('name', 'NewsAPI')
            if not title or title == '[Removed]':
                continue

            h = make_hash(title, url)
            if h in seen or is_fuzzy_duplicate(title):
                seen.add(h)
                continue

            mark_sent(title, h)
            send_headline(f'NewsAPI/{src}', title, url, desc)
            count += 1

    except Exception as e:
        log(f'NewsAPI err: {e}')

    if count:
        log(f'NewsAPI ({query[:30]}): sent {count} headlines')
    return count


# ═══════════════════════════════════════════════════════════════════
#  SOURCE 3: POLYGON.IO  (Tertiary — ticker-specific, free tier)
# ═══════════════════════════════════════════════════════════════════

_polygon_ticker_idx = 0

def fetch_polygon():
    """Fetch ticker news from Polygon.io (rotates tickers to save quota)."""
    global _polygon_ticker_idx
    if not POLYGON_KEY:
        return 0
    count = 0

    all_tickers = US_TICKERS + INDIA_SYMBOLS
    ticker = all_tickers[_polygon_ticker_idx % len(all_tickers)]
    _polygon_ticker_idx += 1

    try:
        r = requests.get(
            f'https://api.polygon.io/v2/reference/news',
            params={
                'ticker': ticker,
                'limit': 5,
                'order': 'desc',
                'sort': 'published_utc',
                'apiKey': POLYGON_KEY,
            },
            timeout=15,
        )
        if r.status_code != 200:
            log(f'Polygon HTTP {r.status_code}')
            return 0

        data = r.json()
        for art in data.get('results', []):
            title = (art.get('title') or '').strip()
            url   = art.get('article_url', '')
            desc  = (art.get('description') or '')[:200]
            pub   = art.get('publisher', {}).get('name', 'Polygon')
            if not title:
                continue

            h = make_hash(title, url)
            if h in seen or is_fuzzy_duplicate(title):
                seen.add(h)
                continue

            mark_sent(title, h)
            send_headline(f'Polygon/{pub}', title, url, desc)
            count += 1

    except Exception as e:
        log(f'Polygon err: {e}')

    if count:
        log(f'Polygon ({ticker}): sent {count} headlines')
    return count


# ═══════════════════════════════════════════════════════════════════
#  FII/DII DAILY REPORT  (NSE India scrape)
# ═══════════════════════════════════════════════════════════════════

def fetch_fiidii():
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.nseindia.com',
        }
        s = requests.Session()
        s.get('https://www.nseindia.com', headers=headers, timeout=10)
        r = s.get('https://www.nseindia.com/api/fiidiiTradeReact',
                  headers=headers, timeout=10)
        data = r.json()

        fii_buy = fii_sell = fii_net = 0
        dii_buy = dii_sell = dii_net = 0

        for row in data:
            cat = row.get('category', '')
            if 'FII' in cat or 'FPI' in cat:
                fii_buy  = row.get('buyValue', 0)
                fii_sell = row.get('sellValue', 0)
                fii_net  = row.get('netValue', 0)
            if cat == 'DII':
                dii_buy  = row.get('buyValue', 0)
                dii_sell = row.get('sellValue', 0)
                dii_net  = row.get('netValue', 0)

        fii_dir = '🟢 BUYING' if fii_net > 0 else '🔴 SELLING'
        dii_dir = '🟢 BUYING' if dii_net > 0 else '🔴 SELLING'

        if fii_net > 0 and dii_net > 0:
            outlook = '🟢 BULLISH'
        elif fii_net < 0 and dii_net < 0:
            outlook = '🔴 BEARISH'
        else:
            outlook = '🟡 MIXED'

        tg(
            f'📊 <b>FII/DII DAILY REPORT</b>\n'
            f'{datetime.now().strftime("%d %b %Y")}\n\n'
            f'<b>FII/FPI:</b>\n'
            f'  Buy : ₹{round(fii_buy, 2)} Cr\n'
            f'  Sell: ₹{round(fii_sell, 2)} Cr\n'
            f'  Net : ₹{round(fii_net, 2)} Cr ({fii_dir})\n\n'
            f'<b>DII:</b>\n'
            f'  Buy : ₹{round(dii_buy, 2)} Cr\n'
            f'  Sell: ₹{round(dii_sell, 2)} Cr\n'
            f'  Net : ₹{round(dii_net, 2)} Cr ({dii_dir})\n\n'
            f'<b>OUTLOOK:</b> {outlook}'
        )
        log('FII/DII report sent')
    except Exception as e:
        log(f'FII/DII err: {e}')


# ═══════════════════════════════════════════════════════════════════
#  MAIN LOOP — Multi-source scheduler
# ═══════════════════════════════════════════════════════════════════

def startup_message():
    """Send bot status on startup."""
    sources = []
    if FINNHUB_KEY:
        sources.append('Finnhub (every 30s)')
    if NEWSAPI_KEY:
        sources.append('NewsAPI (every 5min)')
    if POLYGON_KEY:
        sources.append('Polygon.io (every 2min)')

    if not sources:
        log('⚠️  NO API KEYS SET! Set at least one: FINNHUB_KEY, NEWSAPI_KEY, POLYGON_KEY')
        tg('⚠️ Bot started but NO API keys configured!\nSet env vars: FINNHUB_KEY, NEWSAPI_KEY, POLYGON_KEY')
        return

    tg(
        '🚀 <b>Market News Bot v2 Started!</b>\n\n'
        f'📡 <b>Sources ({len(sources)}):</b>\n'
        + '\n'.join(f'  • {s}' for s in sources)
        + '\n\n'
        f'🎯 Tracking: {len(US_TICKERS)} US + {len(INDIA_SYMBOLS)} India tickers\n'
        f'📊 FII/DII report daily at 4:00 PM IST\n'
        f'🔑 Keywords: {len(KEYWORDS)} active filters\n\n'
        f'<i>Cold start: first cycle indexes existing headlines without sending.</i>'
    )


def cold_start():
    """
    CRITICAL FIX: On first run, silently index all current headlines
    so we only send NEW ones from the next cycle onward.
    This prevents the "spam dump on boot" problem.
    """
    global seen
    if os.path.exists(SEEN_FILE):
        log('Seen file exists, skipping cold start')
        return

    log('Cold start: indexing existing headlines (no sends)...')
    original_tg = globals()['tg']

    # Temporarily disable Telegram sends
    def noop_tg(msg):
        pass
    globals()['tg'] = noop_tg

    # Run all sources once to populate seen set
    if FINNHUB_KEY:
        fetch_finnhub()
        log(f'  Finnhub indexed ({len(seen)} hashes)')
    if NEWSAPI_KEY:
        fetch_newsapi()
        log(f'  NewsAPI indexed ({len(seen)} hashes)')
    if POLYGON_KEY:
        fetch_polygon()
        log(f'  Polygon indexed ({len(seen)} hashes)')

    # Restore Telegram
    globals()['tg'] = original_tg
    save_seen(seen)
    log(f'Cold start done. {len(seen)} headlines indexed.')


if __name__ == '__main__':
    log('News Bot v2 starting...')

    # Validate config
    if not TOKEN:
        log('ERROR: TELEGRAM_TOKEN not set!')
    if not CHAT:
        log('ERROR: TELEGRAM_CHAT not set!')

    startup_message()
    cold_start()

    # Track last run times per source
    last_finnhub  = 0.0
    last_newsapi  = 0.0
    last_polygon  = 0.0
    fii_sent      = False
    save_counter  = 0

    while True:
        try:
            now = time.time()
            utcnow = datetime.now(timezone.utc)
            total = 0

            # ── Finnhub: every 30s ──
            if FINNHUB_KEY and (now - last_finnhub) >= FINNHUB_INTERVAL:
                last_finnhub = now
                total += fetch_finnhub()

            # ── NewsAPI: every 5 min ──
            if NEWSAPI_KEY and (now - last_newsapi) >= NEWSAPI_INTERVAL:
                last_newsapi = now
                total += fetch_newsapi()

            # ── Polygon: every 2 min ──
            if POLYGON_KEY and (now - last_polygon) >= POLYGON_INTERVAL:
                last_polygon = now
                total += fetch_polygon()

            # ── FII/DII at 4:00 PM IST (10:30 UTC) ──
            if utcnow.hour == FIIDII_HOUR_UTC and FIIDII_MINUTE_UTC <= utcnow.minute < FIIDII_MINUTE_UTC + 5:
                if not fii_sent:
                    fii_sent = True
                    fetch_fiidii()

            # Reset daily flags at midnight UTC
            if utcnow.hour == 0 and utcnow.minute < 5:
                fii_sent = False

            # Save hashes every 5 cycles
            save_counter += 1
            if save_counter >= 5:
                save_seen(seen)
                save_counter = 0

            # Sleep 10s between checks (sources have their own intervals)
            time.sleep(10)

        except KeyboardInterrupt:
            log('Shutting down...')
            save_seen(seen)
            break
        except Exception as e:
            log(f'Main loop err: {e}')
            time.sleep(30)
