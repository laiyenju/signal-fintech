"""SIGNAL 資料源名冊（單一事實來源）。
fetch_news.py 用它抓資料；newsroom.py 用它列出「本輪沒更新的源」。
新增來源時記得同步更新 index.html 的 SOURCES 物件（追蹤來源清單顯示用）。

scope: "tw" | "global"
digest=True：TLDR 型電子報（抓當期網頁再拆成獨立候選）
policy:
  - rss_only：只走 RSS
  - rss_primary_readwise_fallback：RSS 失敗或 48h 無量時，用 Readwise CLI 依 match 補抓
  - readwise_only：只走 Readwise（需 readwise_match）
readwise_match: {"domains": [...], "site_names": [...]} 對 Reader feed 的 site_name / source_url host
"""

# 預設 policy；單源可覆寫
DEFAULT_POLICY = "rss_only"

FEEDS = [
    # ---- 新聞媒體 ----
    {"name": "TechCrunch Fintech", "scope": "global",
     "url": "https://techcrunch.com/category/fintech/feed/",
     "readwise_match": {"domains": ["techcrunch.com"], "site_names": ["techcrunch.com"]}},
    {"name": "Bankless", "scope": "global",
     "url": "https://www.bankless.com/feed",
     "readwise_match": {"domains": ["bankless.com"], "site_names": ["bankless.com"]}},
    {"name": "PYMNTS", "scope": "global",
     "url": "https://www.pymnts.com/feed/",
     "readwise_match": {"domains": ["pymnts.com"], "site_names": ["pymnts.com"]}},
    {"name": "Finextra", "scope": "global",
     "url": "https://www.finextra.com/rss/headlines.aspx",
     "readwise_match": {"domains": ["finextra.com"], "site_names": ["finextra.com"]}},
    {"name": "Banking Dive", "scope": "global",
     "url": "https://www.bankingdive.com/feeds/news/",
     "readwise_match": {"domains": ["bankingdive.com"], "site_names": ["bankingdive.com"]}},
    {"name": "The Fintech Times", "scope": "global",
     "url": "https://www.thefintechtimes.com/feed/",
     "readwise_match": {"domains": ["thefintechtimes.com"], "site_names": ["thefintechtimes.com"]}},
    # CoinDesk：URL 不可帶尾隨 `/`（會 308 到無斜線版）；Python 3.9 對 308 不穩。
    # 保留 Readwise fallback 作雙保險。
    {"name": "CoinDesk", "scope": "global",
     "url": "https://www.coindesk.com/arc/outboundfeeds/rss",
     "policy": "rss_primary_readwise_fallback",
     "readwise_match": {"domains": ["coindesk.com"], "site_names": ["coindesk.com"]}},
    {"name": "The Block", "scope": "global",
     "url": "https://www.theblock.co/rss.xml",
     "readwise_match": {"domains": ["theblock.co"], "site_names": ["theblock.co"]}},
    {"name": "NYT Dealbook", "scope": "global",
     "url": "https://rss.nytimes.com/services/xml/rss/nyt/Dealbook.xml",
     "readwise_match": {"domains": ["nytimes.com"], "site_names": ["nytimes.com"]}},
    {"name": "NYT Economy", "scope": "global",
     "url": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
     "readwise_match": {"domains": ["nytimes.com"], "site_names": ["nytimes.com"]}},
    {"name": "NYT Technology", "scope": "global",
     "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
     "readwise_match": {"domains": ["nytimes.com"], "site_names": ["nytimes.com"]}},
    {"name": "Hacker News", "scope": "global",
     "url": "https://news.ycombinator.com/rss",
     "readwise_match": {"domains": ["news.ycombinator.com", "ycombinator.com"],
                        "site_names": ["news.ycombinator.com"]}},
    {"name": "Techmeme", "scope": "global",
     "url": "https://www.techmeme.com/feed.xml",
     "readwise_match": {"domains": ["techmeme.com"], "site_names": ["techmeme.com"]}},
    {"name": "經濟日報", "scope": "tw",
     "url": "https://money.udn.com/rssfeed/news/1001?ch=money",
     "readwise_match": {"domains": ["money.udn.com", "udn.com"], "site_names": ["money.udn.com"]}},
    {"name": "科技新報", "scope": "tw",
     "url": "https://technews.tw/feed/",
     "readwise_match": {"domains": ["technews.tw"], "site_names": ["technews.tw"]}},
    {"name": "公視新聞", "scope": "tw",
     "url": "https://news.pts.org.tw/xml/newsfeed.xml",
     "readwise_match": {"domains": ["pts.org.tw", "news.pts.org.tw"],
                        "site_names": ["pts.org.tw", "news.pts.org.tw"]}},
    # Yahoo 財經 RSS 常只有較舊條目；暫維持 rss_only（Reader 未訂）。若長期 stale 再換 URL 或訂閱。
    {"name": "Yahoo 財經", "scope": "tw",
     "url": "https://tw.news.yahoo.com/rss/finance",
     "readwise_match": {"domains": ["tw.news.yahoo.com", "yahoo.com"],
                        "site_names": ["tw.news.yahoo.com"]}},
    {"name": "中央社 CNA（科技）", "scope": "tw",
     "url": "https://feeds.feedburner.com/rsscna/technology",
     "readwise_match": {"domains": ["cna.com.tw"], "site_names": ["cna.com.tw"]}},
    {"name": "中央社 CNA（財經）", "scope": "tw",
     "url": "https://feeds.feedburner.com/rsscna/finance",
     "readwise_match": {"domains": ["cna.com.tw"], "site_names": ["cna.com.tw"]}},
    # ---- 分析評論（digest）----
    {"name": "TLDR Fintech", "scope": "global",
     "url": "https://tldr.tech/api/rss/fintech", "digest": True,
     "readwise_match": {"domains": ["tldr.tech"], "site_names": ["tldr.tech"]}},
    {"name": "TLDR AI", "scope": "global",
     "url": "https://tldr.tech/api/rss/ai", "digest": True,
     "readwise_match": {"domains": ["tldr.tech"], "site_names": ["tldr.tech"]}},
    {"name": "TLDR Dev", "scope": "global",
     "url": "https://tldr.tech/api/rss/dev", "digest": True,
     "readwise_match": {"domains": ["tldr.tech"], "site_names": ["tldr.tech"]}},
]


def feed_policy(feed: dict) -> str:
    return feed.get("policy") or DEFAULT_POLICY
