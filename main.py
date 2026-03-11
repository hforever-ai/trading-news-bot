import feedparser, requests, time, hashlib
from xml.etree import ElementTree as ET
from datetime import datetime

TOKEN     = '8635295437:AAEXsu4d4gceAVNqHicQ5Jfb36lI6Yqw1tI'
CHAT      = '846560537'
BZ        = 'bz.FSQEII7ABTQXIPTILNMZLGCKXEJPWFYH'

KEYWORDS = [
    'stock','market','earnings','fed','nasdaq','crash','bitcoin',
    'rate','inflation','ipo','merger','rally','plunge','surge',
    'nifty','sensex','rbi','sebi','bse','nse','banknifty',
    'gdp','trade','tariff','acquisition','bankruptcy','dividend'
]

FEEDS = {
    'Reuters'     :'https://feeds.reuters.com/reuters/businessNews',
    'CNBC'        :'https://www.cnbc.com/id/100003114/device/rss/rss.html',
    'MarketWatch' :'https://feeds.marketwatch.com/marketwatch/topstories/',
    'Yahoo Finance':'https://finance.yahoo.com/news/rssindex',
    'Bloomberg'   :'https://feeds.bloomberg.com/markets/news.rss',
    'ET Markets'  :'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
    'Moneycontrol':'https://www.moneycontrol.com/rss/MCtopnews.xml',
    'SEC EDGAR'   :'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&dateb=&owner=include&count=10&output=atom',
}

seen = set()

def tg(m):
    try:
        requests.post('https://api.telegram.org/bot'+TOKEN+'/sendMessage',
            json={'chat_id':CHAT,'text':m}, timeout=10)
    except Exception as e:
        print('TG err:'+str(e), flush=True)

def fetch_rss():
    for src, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:5]:
                t = e.get('title','')
                l = e.get('link','')
                h = hashlib.md5((t+l).encode()).hexdigest()
                if h not in seen and any(k in t.lower() for k in KEYWORDS):
                    seen.add(h)
                    tg('['+src+']\n'+t+'\n'+l)
                    time.sleep(0.5)
        except Exception as e:
            print(src+' err:'+str(e), flush=True)

def fetch_benzinga():
    try:
        r = requests.get('https://api.benzinga.com/api/v2/news',
            params={'token':BZ,'pageSize':'10'}, timeout=10)
        root = ET.fromstring(r.text)
        for item in root.findall('item'):
            t = item.findtext('title','')
            u = item.findtext('url','')
            h = hashlib.md5(t.encode()).hexdigest()
            if h not in seen and any(k in t.lower() for k in KEYWORDS):
                seen.add(h)
                tg('[Benzinga]\n'+t+'\n'+u)
                time.sleep(0.5)
    except Exception as e:
        print('Benzinga err:'+str(e), flush=True)

def fetch_fiidii():
    try:
        headers = {
            'User-Agent':'Mozilla/5.0',
            'Accept':'application/json',
            'Referer':'https://www.nseindia.com'
        }
        s = requests.Session()
        s.get('https://www.nseindia.com', headers=headers, timeout=10)
        r = s.get('https://www.nseindia.com/api/fiidiiTradeReact',
                  headers=headers, timeout=10)
        data = r.json()
        fii_buy=fii_sell=fii_net=dii_buy=dii_sell=dii_net=0
        for row in data:
            cat = row.get('category','')
            if 'FII' in cat or 'FPI' in cat:
                fii_buy=row.get('buyValue',0)
                fii_sell=row.get('sellValue',0)
                fii_net=row.get('netValue',0)
            if cat=='DII':
                dii_buy=row.get('buyValue',0)
                dii_sell=row.get('sellValue',0)
                dii_net=row.get('netValue',0)
        fii_dir='BUYING' if fii_net>0 else 'SELLING'
        dii_dir='BUYING' if dii_net>0 else 'SELLING'
        outlook='BULLISH' if fii_net>0 and dii_net>0 else 'BEARISH' if fii_net<0 and dii_net<0 else 'MIXED'
        tg(
            'FII/DII DAILY REPORT\n'
            +datetime.now().strftime('%d %b %Y')+'\n\n'
            +'FII/FPI:\n'
            +'  Buy : '+str(round(fii_buy,2))+' Cr\n'
            +'  Sell: '+str(round(fii_sell,2))+' Cr\n'
            +'  Net : '+str(round(fii_net,2))+' Cr ('+fii_dir+')\n\n'
            +'DII:\n'
            +'  Buy : '+str(round(dii_buy,2))+' Cr\n'
            +'  Sell: '+str(round(dii_sell,2))+' Cr\n'
            +'  Net : '+str(round(dii_net,2))+' Cr ('+dii_dir+')\n\n'
            +'OUTLOOK: '+outlook
        )
    except Exception as e:
        tg('FII/DII error: '+str(e))

print('News Bot started!', flush=True)
tg(
    'Market News Bot Started!\n'
    +'Sources: Reuters, CNBC, MarketWatch,\n'
    +'Yahoo Finance, Bloomberg, ET Markets,\n'
    +'Moneycontrol, SEC + Benzinga Pro\n'
    +'FII/DII daily at 4:00pm IST'
)

fii_sent = False

while True:
    try:
        now = datetime.now()
        fetch_rss()
        fetch_benzinga()
        # FII/DII at 4pm IST = 10:30 UTC
        if now.hour==10 and now.minute>=30 and now.minute<33:
            if not fii_sent:
                fii_sent = True
                fetch_fiidii()
        if now.hour==0:
            fii_sent = False
        time.sleep(15)
    except Exception as e:
        print('Main loop err:'+str(e), flush=True)
        time.sleep(30)
