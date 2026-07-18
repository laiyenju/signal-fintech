"""SIGNAL 資料源名冊（單一事實來源）。
fetch_news.py 用它抓 RSS；newsroom.py 用它列出「本輪沒更新的源」。
新增來源時記得同步更新 index.html 的 SOURCES 物件（追蹤來源清單顯示用）。
scope: "tw" | "global"；digest=True 表示 TLDR 型電子報（抓當期網頁再拆成獨立候選）。"""

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
    # ---- 分析評論（digest）----
    {"name": "TLDR Fintech", "scope": "global", "url": "https://tldr.tech/api/rss/fintech", "digest": True},
    {"name": "TLDR AI", "scope": "global", "url": "https://tldr.tech/api/rss/ai", "digest": True},
    {"name": "TLDR Dev", "scope": "global", "url": "https://tldr.tech/api/rss/dev", "digest": True},
]
