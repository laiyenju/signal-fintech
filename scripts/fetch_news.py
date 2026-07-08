"""
fetch_news.py
每小時執行的第一步：抓取「來源盤點.md」中已確認有 RSS 的來源，
把過去 48 小時內的項目整理成 raw_items.json，供 select_and_write.py 使用。

需要套件：feedparser
    pip install feedparser --break-system-packages

用法：
    python fetch_news.py
輸出：
    raw_items.json（與本檔案同目錄）
"""

import json
import time
from datetime import datetime, timezone, timedelta
import feedparser

# ---------------------------------------------------------------------------
# 來源清單：只放「已確認有 RSS」的來源（對應 來源盤點.md 的 ✅ / 🟡 項目）
# scope: "tw" | "global"（決定要進網站的哪一邊清單）
# 有些來源（金管會、CNA）官方提供的是「訂閱頁」而非單一 feed 網址，
# 這裡先留一個明顯的 TODO，麻煩你到訂閱頁挑一個實際的分類 feed 網址填進來。
# ---------------------------------------------------------------------------
FEEDS = [
    # ---- 新聞媒體 ----
    {"name": "TechCrunch Fintech", "scope": "global", "url": "https://techcrunch.com/category/fintech/feed/"},
    {"name": "Bankless", "scope": "global", "url": "https://www.bankless.com/feed"},
    {"name": "PYMNTS", "scope": "global", "url": "https://www.pymnts.com/feed/"},
    {"name": "Finextra", "scope": "global", "url": "https://www.finextra.com/rss/headlines.aspx"},
    {"name": "Banking Dive", "scope": "global", "url": "https://www.bankingdive.com/feeds/news/"},
    {"name": "The Fintech Times", "scope": "global", "url": "https://www.thefintechtimes.com/feed/"},
    {"name": "CoinDesk", "scope": "global", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "經濟日報", "scope": "tw", "url": "https://money.udn.com/rssfeed/news/1001?ch=money"},
    {"name": "科技新報", "scope": "tw", "url": "https://technews.tw/feed/"},
    {"name": "公視新聞", "scope": "tw", "url": "https://news.pts.org.tw/xml/newsfeed.xml"},
    {"name": "Yahoo 財經", "scope": "tw", "url": "https://tw.news.yahoo.com/rss/finance"},
    {"name": "中央社 CNA（科技）", "scope": "tw", "url": "https://feeds.feedburner.com/rsscna/technology"},
    {"name": "中央社 CNA（財經）", "scope": "tw", "url": "https://feeds.feedburner.com/rsscna/finance"},

    # ---- 分析評論 ----
    {"name": "TLDR Fintech", "scope": "global", "url": "https://tldr.tech/api/rss/fintech"},

    # ---- 監管機構 ----
    {"name": "美國 SEC", "scope": "global", "url": "https://www.sec.gov/news/pressreleases.rss"},
    {"name": "歐盟 ESMA", "scope": "global", "url": "https://www.esma.europa.eu/rss.xml"},
    {"name": "歐盟 EBA", "scope": "global", "url": "https://www.eba.europa.eu/news-press/news/rss.xml"},
    {"name": "英國 FCA", "scope": "global", "url": "https://www.fca.org.uk/news/rss.xml"},
    {"name": "日本金融庁", "scope": "global", "url": "https://www.fsa.go.jp/fsaEnNewsList_rss2.xml"},
    {"name": "台灣金管會（新聞稿1）", "scope": "tw", "url": "https://www.fsc.gov.tw/RSS/Messages?serno=201202290001&language=chinese"},
    {"name": "台灣金管會（新聞稿2）", "scope": "tw", "url": "https://www.fsc.gov.tw/RSS/Messages?serno=201202290009&language=chinese"},

    # ---- 公司來源 ----
    {"name": "Stripe Blog", "scope": "global", "url": "https://stripe.com/blog/feed.rss"},
    {"name": "PayPal Newsroom", "scope": "global", "url": "https://newsroom.paypal-corp.com/news?pagetemplate=rss"},
    {"name": "MaiCoin Blog", "scope": "tw", "url": "https://blog.maicoin.com/feed/"},
]

LOOKBACK_HOURS = 48  # 只保留過去 48 小時內的項目，避免每次都重複收到舊文章


def parse_published(entry):
    """feedparser 的時間欄位不一定叫同一個名字，這裡盡量抓得到就用。"""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def fetch_all():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items = []

    for feed in FEEDS:
        if feed["url"].startswith("PLEASE_FILL_IN"):
            print(f"[skip] {feed['name']}：尚未填入實際 feed 網址")
            continue

        try:
            parsed = feedparser.parse(feed["url"])
        except Exception as e:
            print(f"[error] {feed['name']}：{e}")
            continue

        if parsed.bozo and not parsed.entries:
            print(f"[warn] {feed['name']}：feed 可能解析失敗（{parsed.bozo_exception}）")
            continue

        for entry in parsed.entries:
            published = parse_published(entry)
            if published and published < cutoff:
                continue  # 太舊的先跳過

            items.append({
                "source": feed["name"],
                "scope": feed["scope"],
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", entry.get("description", "")).strip(),
                "published": published.isoformat() if published else None,
            })

        print(f"[ok] {feed['name']}：{len(parsed.entries)} 則")

    return items


if __name__ == "__main__":
    items = fetch_all()
    with open("raw_items.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"\n共 {len(items)} 則，已寫入 raw_items.json")
