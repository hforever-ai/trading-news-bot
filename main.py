import feedparser, requests, time, hashlib, json, os
from xml.etree import ElementTree as ET
from datetime import datetime

# ─── CONFIG ─────────────────────────────────────────────────────────
# Set these as environment variables on your host (Heroku, Railway, etc.)
# Falls back to hardcoded values if env vars not set.
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8635295437:AAEXsu4d4gceAVNqHicQ5Jfb36lI6Yqw1tI')
CHAT  = os.environ.get('TELEGRAM_CHAT',  '846560537')
BZ    = os.environ.get('BENZINGA_KEY',    'bz.FSQEII7ABTQXIPTILNMZLGCKXEJPWFYH')

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

# ─── RSS FEEDS (Verified Working — US + India) ─────────────────────
FEEDS = {
    # ── US Sources ──
    'CNBC Business'   : 'https://www.cnbc.com/id/10001147/device/rss/rss.html',
    'CNBC Economy'    : 'https://www.cnbc.com/id/20910258/device/rss/rss.html',
    'CNBC Earnings'   : 'https://www.cnbc.com/id/15839135/device/rss/rss.html',
    'MarketWatch'     : 'https://feeds.marketwatch.com/marketwatch/topstories/',
    'Nasdaq'          : 'https://www.nasdaq.com/feed/nasdaq-original/rss.xml',
    'Investing.com'   : 'https://www.investing.com/rss/news.rss',
    'Seeking Alpha'   : 'https://seekingalpha.com/feed.xml',
    'Benzinga'        : 'https://feeds.benzinga.com/benzinga',
    'TheStreet'       : 'https://www.thestreet.com/.rss/full',
    'Motley Fool'     : 'https://www.fool.com/a/feeds/partner/google-news-feed/article/.aspx',
    'Fed Reserve'     : 'https://www.federalreserve.gov/feeds/press_all.xml',
    # ── India Sources ──
    'ET Markets'      : 'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
    'Moneycontrol'    : 'https://www.moneycontrol.com/rss/MCtopnews.xml',
    'Business Std'    : 'https://www.business-standard.com/rss/markets-106.rss',
    'Hindu BizLine'   : 'https://www.thehindubusinessline.com/markets/feeder/default.rss',
    'Livemint Markets': 'https://www.livemint.com/rss/markets',
}

# ─── PERSISTENT DEDUP (survives restarts) ──────────────────────────
SEEN_FILE = 'seen_hashes.json'
MAX_SEEN  = 5000  # cap to avoid unbounded file growth

def load_seen():
    """Load seen hashes from disk so restarts don't re-send old news."""
    try:
        with open(SEEN_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('hashes', []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen(seen_set):
    """Persist seen hashes to disk."""
    hashes = list(seen_set)
    if len(hashes) > MAX_SEEN:
        hashes = hashes[-MAX_SEEN:]
    try:
        with open(SEEN_FILE, 'w') as f:
            json.dump({'hashes': hashes, 'updated': datetime.now().isoformat()}, f)
    except Exception as e:
        print(f'Save seen err: {e}', flush=True)

seen = load_seen()

# ─── TELEGRAM ──────────────────────────────────────────────────────
def tg(msg):
    """Send a message to Telegram with retry and rate-limit handling."""
    for attempt in range(2):
        try:
            r = requests.post(
                f'https://api.telegram.org/bot{TOKEN}/sendMessage',
                json={'chat_id': CHAT, 'text': msg, 'disable_web_page_preview': True},
                timeout=15,
            )
            if r.status_code == 429:
                retry_after = r.json().get('parameters', {}).get('retry_after', 5)
                print(f'TG rate limited, waiting {retry_after}s', flush=True)
                time.sleep(retry_after)
                continue
            return
        except Exception as e:
            print(f'TG err (attempt {attempt+1}): {e}', flush=True)
            time.sleep(2)

def matches_keywords(title):
    """Check if title contains any keyword (case-insensitive)."""
    t = title.lower()
    return any(kw in t for kw in KEYWORDS)

# ─── RSS FETCHER ───────────────────────────────────────────────────
def fetch_rss():
    """Fetch all RSS feeds and send matching, unseen headlines."""
    global seen
    new_count = 0
    for src, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                print(f'{src}: feed error (bozo={feed.bozo_exception})', flush=True)
                continue

            for entry in feed.entries[:8]:
                title = entry.get('title', '').strip()
                link  = entry.get('link', '').strip()
                if not title:
                    continue

                h = hashlib.md5((title + link).encode()).hexdigest()
                if h in seen:
                    continue

                # Mark as seen regardless of match (prevents re-checking)
                seen.add(h)

                if matches_keywords(title):
                    new_count += 1
                    tg(f'📰 [{src}]\n{title}\n{link}')
                    time.sleep(0.5)

        except Exception as e:
            print(f'{src} err: {e}', flush=True)

    if new_count > 0:
        save_seen(seen)
        print(f'Sent {new_count} new headlines', flush=True)

# ─── BENZINGA API FETCHER ──────────────────────────────────────────
def fetch_benzinga():
    """Fetch news from Benzinga Pro API."""
    global seen
    try:
        r = requests.get(
            'https://api.benzinga.com/api/v2/news',
            params={'token': BZ, 'pageSize': '10'},
            timeout=15,
        )
        if r.status_code != 200:
            print(f'Benzinga HTTP {r.status_code}', flush=True)
            return

        root = ET.fromstring(r.text)
        for item in root.findall('item'):
            title = (item.findtext('title') or '').strip()
            url   = (item.findtext('url') or '').strip()
            h = hashlib.md5(title.encode()).hexdigest()
            if h not in seen and matches_keywords(title):
                seen.add(h)
                tg(f'📰 [Benzinga Pro]\n{title}\n{url}')
                time.sleep(0.5)
    except Exception as e:
        print(f'Benzinga err: {e}', flush=True)

# ─── FII/DII DAILY REPORT ─────────────────────────────────────────
def fetch_fiidii():
    """Scrape NSE India for FII/DII buy-sell data."""
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
            f'📊 FII/DII DAILY REPORT\n'
            f'{datetime.now().strftime("%d %b %Y")}\n\n'
            f'FII/FPI:\n'
            f'  Buy : ₹{round(fii_buy, 2)} Cr\n'
            f'  Sell: ₹{round(fii_sell, 2)} Cr\n'
            f'  Net : ₹{round(fii_net, 2)} Cr ({fii_dir})\n\n'
            f'DII:\n'
            f'  Buy : ₹{round(dii_buy, 2)} Cr\n'
            f'  Sell: ₹{round(dii_sell, 2)} Cr\n'
            f'  Net : ₹{round(dii_net, 2)} Cr ({dii_dir})\n\n'
            f'OUTLOOK: {outlook}'
        )
    except Exception as e:
        print(f'FII/DII err: {e}', flush=True)

# ─── DAILY FEED HEALTH CHECK ──────────────────────────────────────
def feed_health_check():
    """Once a day, report which feeds are alive vs dead."""
    alive, dead = [], []
    for src, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                alive.append(src)
            else:
                dead.append(src)
        except Exception:
            dead.append(src)

    msg = f'🩺 Daily Feed Health Check\n\n'
    msg += f'✅ Working ({len(alive)}):\n' + (', '.join(alive) or 'None')
    msg += f'\n\n❌ Down ({len(dead)}):\n' + (', '.join(dead) or 'None')
    tg(msg)

# ─── MAIN LOOP ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print('News Bot started!', flush=True)
    tg(
        '🚀 Market News Bot Started!\n\n'
        f'📡 Sources: {len(FEEDS)} RSS feeds + Benzinga Pro\n'
        '🇺🇸 US: CNBC, MarketWatch, Nasdaq, Seeking Alpha,\n'
        '    TheStreet, Motley Fool, Investing.com, Fed\n'
        '🇮🇳 India: ET Markets, Moneycontrol, Business Std,\n'
        '    Hindu BizLine, Livemint\n\n'
        '📊 FII/DII report daily at 4:00 PM IST\n'
        '🩺 Feed health check daily at 8:00 AM IST'
    )

    fii_sent    = False
    health_sent = False

    while True:
        try:
            now = datetime.utcnow()

            # Fetch news every loop (~60s)
            fetch_rss()
            fetch_benzinga()

            # FII/DII at 4:00 PM IST = 10:30 UTC
            if now.hour == 10 and 30 <= now.minute < 35:
                if not fii_sent:
                    fii_sent = True
                    fetch_fiidii()

            # Feed health check at 8:00 AM IST = 2:30 UTC
            if now.hour == 2 and 30 <= now.minute < 35:
                if not health_sent:
                    health_sent = True
                    feed_health_check()

            # Reset daily flags at midnight UTC
            if now.hour == 0 and now.minute < 5:
                fii_sent    = False
                health_sent = False

            # Save hashes periodically
            save_seen(seen)

            time.sleep(60)

        except Exception as e:
            print(f'Main loop err: {e}', flush=True)
            time.sleep(30)
