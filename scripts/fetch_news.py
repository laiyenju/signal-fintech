"""
fetch_news.py
排程任務每次執行的第一步：抓取 FEEDS 清單中的來源，
把過去 48 小時內的項目整理成 raw_items.json，供排程任務（見 排程任務指令.md）讀取後自行選稿改寫。

需要套件：feedparser
    pip install feedparser --break-system-packages

用法：
    python fetch_news.py
輸出：
    raw_items.json（與本檔案同目錄）
"""

import calendar
import html
import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import feedparser

# ---------------------------------------------------------------------------
# 來源清單：只放「已確認有 RSS」的來源
# scope: "tw" | "global"（決定要進網站的哪一邊清單）
# 新增來源時記得同步更新 index.html 的 SOURCES 物件（追蹤來源清單顯示用）
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
    {"name": "The Block", "scope": "global", "url": "https://www.theblock.co/rss.xml"},
    # Bloomberg Markets RSS（feeds.bloomberg.com）已確認無法抓到內容，停用。
    # Bloomberg 報導仍可透過 TLDR AI digest 轉入。
    {"name": "NYT Dealbook", "scope": "global", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Dealbook.xml"},
    {"name": "NYT Economy", "scope": "global", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"},
    {"name": "NYT Technology", "scope": "global", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"},
    {"name": "Hacker News", "scope": "global", "url": "https://news.ycombinator.com/rss"},
    {"name": "Techmeme", "scope": "global", "url": "https://www.techmeme.com/feed.xml"},
    {"name": "經濟日報", "scope": "tw", "url": "https://money.udn.com/rssfeed/news/1001?ch=money"},
    {"name": "科技新報", "scope": "tw", "url": "https://technews.tw/feed/"},
    {"name": "公視新聞", "scope": "tw", "url": "https://news.pts.org.tw/xml/newsfeed.xml"},
    {"name": "Yahoo 財經", "scope": "tw", "url": "https://tw.news.yahoo.com/rss/finance"},
    {"name": "中央社 CNA（科技）", "scope": "tw", "url": "https://feeds.feedburner.com/rsscna/technology"},
    {"name": "中央社 CNA（財經）", "scope": "tw", "url": "https://feeds.feedburner.com/rsscna/finance"},

    # ---- 分析評論 ----
    # digest: RSS 只有「當期標題＋連結」沒有內文，抓取時會再抓當期網頁，
    # 拆成一則一則的新聞（標題／摘要／原始媒體連結）當作獨立候選
    {"name": "TLDR Fintech", "scope": "global", "url": "https://tldr.tech/api/rss/fintech", "digest": True},
    {"name": "TLDR AI", "scope": "global", "url": "https://tldr.tech/api/rss/ai", "digest": True},
    {"name": "TLDR Dev", "scope": "global", "url": "https://tldr.tech/api/rss/dev", "digest": True},
]
# 社群討論（coverSocial / social）不再走 RSS：改由排程任務在選稿後，
# 用 Algolia HN Search API 逐則反查對應討論串（見 排程任務指令.md 步驟 3）

LOOKBACK_HOURS = 48  # 只保留過去 48 小時內的項目，避免每次都重複收到舊文章


def parse_published(entry):
    """feedparser 的時間欄位不一定叫同一個名字，這裡盡量抓得到就用。"""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


# TLDR 當期網頁裡每則新聞的固定結構：
# <article><a href="原始連結"><h3>標題 (N minute read)</h3></a><div class="newsletter-html">摘要</div></article>
TLDR_ARTICLE_RE = re.compile(
    r'<article[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>\s*<h3>(.*?)</h3>\s*</a>'
    r'\s*<div class="newsletter-html">(.*?)</div>',
    re.S,
)


def strip_utm(url):
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.startswith("utm_")]
    return urlunsplit(p._replace(query=urlencode(q)))


def expand_digest(entry, feed, published):
    """把 TLDR 這類「一期一項」的電子報，拆成一則一則的新聞項目。"""
    try:
        req = Request(entry.link, headers={"User-Agent": "Mozilla/5.0"})
        page = urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        print(f"[warn] {feed['name']}：無法抓取當期網頁 {entry.link}（{e}）")
        return []

    items = []
    for url, title, blurb in TLDR_ARTICLE_RE.findall(page):
        title = html.unescape(re.sub(r"<[^>]+>", "", title))
        title = re.sub(r"\s*\(\d+ minute read\)\s*$", "", title).strip()
        blurb = html.unescape(re.sub(r"<[^>]+>", " ", blurb))
        blurb = re.sub(r"\s+", " ", blurb).strip()
        # 略過贊助內容與 TLDR 站內連結（訂閱、徵才等非新聞項目）
        if "sponsor" in title.lower() or "tldr.tech" in url:
            continue
        items.append({
            "source": feed["name"],
            "scope": feed["scope"],
            "title": title,
            "link": strip_utm(url),
            "summary": blurb,
            "published": published.isoformat() if published else None,
        })
    return items


def fetch_all():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items = []

    for feed in FEEDS:
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

            if feed.get("digest"):
                items.extend(expand_digest(entry, feed, published))
                continue

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
