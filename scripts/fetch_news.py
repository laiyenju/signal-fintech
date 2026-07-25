"""
fetch_news.py
排程任務每次執行的第一步：抓取 FEEDS 清單中的來源，
把過去 48 小時內的項目整理成 raw_items.json，供排程任務（見 排程任務指令.md）讀取後自行選稿改寫。

transport：
  - RSS（預設；含 308 redirect 處理）
  - Readwise CLI fallback（policy=rss_primary_readwise_fallback 且 RSS 無量／失敗時）

需要套件：feedparser
    pip install feedparser --break-system-packages
需要（可選 fallback）：readwise CLI 已 login

用法：
    python fetch_news.py
輸出：
    raw_items.json、feeds_health.json（與本檔案同目錄）
"""

import calendar
import html
import json
import re
import subprocess
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import feedparser

from feeds import FEEDS, feed_policy

LOOKBACK_HOURS = 48
UA = "Mozilla/5.0 (compatible; SIGNAL-fetch/1.0)"


class _HTTP308RedirectHandler(HTTPRedirectHandler):
    """Python 3.9 urllib 不處理 308；部分 feed host 會用 308 去尾隨斜線。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 對 308 與 301/302 一視同仁
        if code == 308:
            code = 301
        return HTTPRedirectHandler.redirect_request(
            self, req, fp, code, msg, headers, newurl)

    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_301(req, fp, code, msg, headers)


_OPENER = build_opener(_HTTP308RedirectHandler)


def parse_published(entry):
    """feedparser 的時間欄位不一定叫同一個名字，這裡盡量抓得到就用。"""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def domain_of(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


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


def fetch_url_bytes(url: str, timeout: int = 30) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with _OPENER.open(req, timeout=timeout) as resp:
        return resp.read()


def expand_digest(entry, feed, published):
    """把 TLDR 這類「一期一項」的電子報，拆成一則一則的新聞項目。"""
    try:
        page = fetch_url_bytes(entry.link).decode("utf-8", "replace")
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
            "via": "rss",
        })
    return items


def parse_rss_body(body: bytes, feed: dict, cutoff: datetime):
    """Parse RSS/Atom bytes into raw_items for one feed."""
    parsed = feedparser.parse(body)
    items = []
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(str(getattr(parsed, "bozo_exception", "bozo parse error")))

    for entry in parsed.entries or []:
        published = parse_published(entry)
        if published and published < cutoff:
            continue

        if feed.get("digest"):
            items.extend(expand_digest(entry, feed, published))
            continue

        items.append({
            "source": feed["name"],
            "scope": feed["scope"],
            "title": (entry.get("title") or "").strip(),
            "link": entry.get("link") or "",
            "summary": (entry.get("summary") or entry.get("description") or "").strip(),
            "published": published.isoformat() if published else None,
            "via": "rss",
        })
    return items, len(parsed.entries or [])


def fetch_rss_feed(feed, cutoff):
    """Returns (items, health_fragment)."""
    url = feed.get("url") or ""
    health = {
        "name": feed["name"],
        "scope": feed["scope"],
        "policy": feed_policy(feed),
        "rss_status": "error",
        "rss_entries": 0,
        "rss_items": 0,
        "rss_error": None,
        "readwise_items": 0,
        "readwise_error": None,
        "status": "error",
    }
    if not url:
        health["rss_status"] = "no_url"
        health["rss_error"] = "missing url"
        return [], health

    try:
        body = fetch_url_bytes(url)
        items, n_entries = parse_rss_body(body, feed, cutoff)
        health["rss_entries"] = n_entries
        health["rss_items"] = len(items)
        health["rss_status"] = "ok" if items else ("empty" if n_entries == 0 else "stale")
        health["status"] = "active_rss" if items else health["rss_status"]
        print(f"[ok] {feed['name']}：rss entries={n_entries} kept={len(items)}")
        return items, health
    except (HTTPError, URLError, TimeoutError, RuntimeError, Exception) as e:
        health["rss_error"] = str(e)[:200]
        health["rss_status"] = "error"
        print(f"[error] {feed['name']}：RSS {e}")
        return [], health


def _match_doc(doc: dict, match: dict) -> bool:
    domains = {d.lower() for d in (match.get("domains") or []) if d}
    sites = {s.lower() for s in (match.get("site_names") or []) if s}
    if not domains and not sites:
        return False
    sn = (doc.get("site_name") or "").lower()
    dom = domain_of(doc.get("source_url") or "")
    if sn and sn in sites:
        return True
    if dom and (dom in domains or any(dom == x or dom.endswith("." + x) for x in domains)):
        return True
    if sn and any(sn == x or sn.endswith(x) for x in domains):
        return True
    return False


def load_readwise_docs(cutoff):
    """Paginate Reader feed via CLI. Returns (docs, error_or_None)."""
    updated_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    docs = []
    cursor = None
    pages = 0
    max_pages = 40
    while pages < max_pages:
        cmd = [
            "readwise", "reader-list-documents",
            "--location", "feed",
            "--updated-after", updated_after,
            "--limit", "100",
            "--response-fields",
            "title,source_url,site_name,category,author,summary,saved_at,created_at",
            "--json",
        ]
        if cursor:
            cmd += ["--page-cursor", cursor]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except FileNotFoundError:
            return [], "readwise CLI not found"
        except subprocess.TimeoutExpired:
            return docs, "readwise CLI timed out" if docs else "readwise CLI timed out (empty)"
        if p.returncode != 0:
            err = (p.stderr or p.stdout or "readwise failed").strip()[:200]
            return docs, err if not docs else None
        try:
            data = json.loads(p.stdout)
        except json.JSONDecodeError as e:
            return docs, f"readwise JSON error: {e}"
        results = data.get("results") or []
        if not results:
            break
        docs.extend(results)
        pages += 1
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
    return docs, None


def items_from_readwise(feed: dict, docs: list) -> list:
    match = feed.get("readwise_match") or {}
    items = []
    for d in docs:
        if not _match_doc(d, match):
            continue
        link = d.get("source_url") or ""
        if not link.startswith("http"):
            continue
        title = (d.get("title") or "").strip()
        if not title:
            continue
        # Prefer saved_at / created_at as published proxy
        published = d.get("saved_at") or d.get("created_at")
        items.append({
            "source": feed["name"],
            "scope": feed["scope"],
            "title": title,
            "link": strip_utm(link),
            "summary": (d.get("summary") or "").strip(),
            "published": published,
            "via": "readwise",
        })
    return items


def needs_readwise(feed: dict, rss_items: list, health: dict) -> bool:
    policy = feed_policy(feed)
    if policy == "readwise_only":
        return True
    if policy == "rss_primary_readwise_fallback":
        if health.get("rss_status") == "error":
            return True
        if not rss_items:
            return True
    return False


def fetch_all(feeds=FEEDS, lookback_hours=LOOKBACK_HOURS):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    all_items = []
    health_rows = []

    # First pass: RSS for everyone (except pure readwise_only)
    rss_by_name = {}
    health_by_name = {}
    want_rw = False
    for feed in feeds:
        policy = feed_policy(feed)
        if policy == "readwise_only":
            h = {
                "name": feed["name"], "scope": feed["scope"], "policy": policy,
                "rss_status": "skipped", "rss_entries": 0, "rss_items": 0,
                "rss_error": None, "readwise_items": 0, "readwise_error": None,
                "status": "pending_readwise",
            }
            rss_by_name[feed["name"]] = []
            health_by_name[feed["name"]] = h
            want_rw = True
            continue
        items, h = fetch_rss_feed(feed, cutoff)
        rss_by_name[feed["name"]] = items
        health_by_name[feed["name"]] = h
        if needs_readwise(feed, items, h):
            want_rw = True

    # One Readwise pull if any feed needs it
    rw_docs, rw_err = ([], None)
    if want_rw:
        print("[info] loading Readwise Reader feed for fallback…")
        rw_docs, rw_err = load_readwise_docs(cutoff)
        if rw_err:
            print(f"[warn] Readwise: {rw_err}")
        else:
            print(f"[ok] Readwise: {len(rw_docs)} docs in window")

    for feed in feeds:
        name = feed["name"]
        items = list(rss_by_name.get(name) or [])
        h = health_by_name[name]
        if needs_readwise(feed, items, h):
            if rw_err and not rw_docs:
                h["readwise_error"] = rw_err
                if not items:
                    h["status"] = "degraded"
            else:
                rw_items = items_from_readwise(feed, rw_docs)
                h["readwise_items"] = len(rw_items)
                if rw_items:
                    # Prefer RSS when both exist; here items empty or we still merge unique links
                    seen = {strip_utm(i.get("link") or "") for i in items}
                    added = 0
                    for it in rw_items:
                        link = strip_utm(it.get("link") or "")
                        if link and link not in seen:
                            items.append(it)
                            seen.add(link)
                            added += 1
                    if added:
                        h["status"] = "active_readwise" if h.get("rss_status") in (
                            "error", "empty", "stale", "skipped") else "active_rss"
                        print(f"[ok] {name}：Readwise +{added}")
                    elif not items:
                        h["status"] = "silent"
                elif not items:
                    h["status"] = "silent"
                    if rw_err:
                        h["readwise_error"] = rw_err
        else:
            if items:
                h["status"] = "active_rss"
            else:
                h["status"] = "silent" if h.get("rss_status") != "error" else "degraded"

        h["windowItems"] = len(items)
        health_rows.append(h)
        all_items.extend(items)

    return all_items, health_rows


if __name__ == "__main__":
    items, health = fetch_all()
    out_dir = __file__.rsplit("/", 1)[0]
    with open(f"{out_dir}/raw_items.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    with open(f"{out_dir}/feeds_health.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lookback_hours": LOOKBACK_HOURS,
            "feeds": health,
        }, f, ensure_ascii=False, indent=2)
    active = sum(1 for h in health if h.get("windowItems"))
    silent = sum(1 for h in health if h.get("status") in ("silent", "degraded") and not h.get("windowItems"))
    print(f"\n共 {len(items)} 則，{active} 源有量 / {silent} 源靜默或降級；已寫入 raw_items.json、feeds_health.json")
