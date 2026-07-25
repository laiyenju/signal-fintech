"""Phase 0：比對 FEEDS 的 RSS 健康度 vs Readwise Reader 是否能補到。

用法：
    python scripts/audit_feeds.py
    python scripts/audit_feeds.py --json scripts/feeds_audit.json

輸出：終端表格 + 可選 JSON。verdict 說明：
    healthy              — RSS 48h 有量
    fix_rss_url          — RSS 失敗/空/嚴重過期，且 Readwise 也沒對上
    use_readwise_fallback— RSS 差，但 Readwise 48h 有對上 → 建議 fallback
    subscribe_in_readwise— RSS 差，Reader 裡完全看不到 → 先訂閱或修 RSS
    rss_ok_readwise_too  — RSS 健康且 Readwise 也有（雙路冗餘可用）
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser

from feeds import FEEDS

LOOKBACK_HOURS = 48
UA = "Mozilla/5.0 (compatible; SIGNAL-audit/1.0)"


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


def guess_match(feed: dict) -> dict:
    """從 FEEDS 條目推斷 Readwise 對照（可被 feed['readwise_match'] 覆寫）。"""
    if feed.get("readwise_match"):
        return feed["readwise_match"]
    url = feed.get("url") or ""
    d = domain_of(url)
    # 常見 feed 託管域名 → 用站名推斷
    aliases = {
        "feeds.feedburner.com": [],  # 無法從 host 推，留給 name
        "rss.nytimes.com": ["nytimes.com"],
        "news.ycombinator.com": ["news.ycombinator.com", "ycombinator.com"],
        "techcrunch.com": ["techcrunch.com"],
        "www.bankless.com": ["bankless.com"],
        "bankless.com": ["bankless.com"],
        "www.pymnts.com": ["pymnts.com"],
        "pymnts.com": ["pymnts.com"],
        "www.finextra.com": ["finextra.com"],
        "finextra.com": ["finextra.com"],
        "www.bankingdive.com": ["bankingdive.com"],
        "bankingdive.com": ["bankingdive.com"],
        "www.thefintechtimes.com": ["thefintechtimes.com"],
        "thefintechtimes.com": ["thefintechtimes.com"],
        "www.coindesk.com": ["coindesk.com"],
        "coindesk.com": ["coindesk.com"],
        "www.theblock.co": ["theblock.co"],
        "theblock.co": ["theblock.co"],
        "www.techmeme.com": ["techmeme.com"],
        "techmeme.com": ["techmeme.com"],
        "money.udn.com": ["money.udn.com", "udn.com"],
        "technews.tw": ["technews.tw"],
        "news.pts.org.tw": ["pts.org.tw", "news.pts.org.tw"],
        "tw.news.yahoo.com": ["tw.news.yahoo.com", "yahoo.com"],
        "tldr.tech": ["tldr.tech"],
    }
    domains = aliases.get(d, [d] if d else [])
    # strip empty
    domains = [x for x in domains if x]
    site_names = list(domains)
    return {"domains": domains, "site_names": site_names}


def parse_published(entry):
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def probe_rss(feed: dict, cutoff: datetime) -> dict:
    url = feed.get("url") or ""
    out = {
        "rss_status": "error",
        "rss_entries": 0,
        "rss_items_48h": 0,
        "rss_latest_at": None,
        "rss_error": None,
    }
    if not url:
        out["rss_status"] = "no_url"
        out["rss_error"] = "missing url"
        return out
    try:
        # feedparser uses urllib; some sites need UA — set via request header if needed
        parsed = feedparser.parse(url, request_headers={"User-Agent": UA})
    except Exception as e:
        out["rss_error"] = str(e)[:200]
        return out

    entries = parsed.entries or []
    out["rss_entries"] = len(entries)
    if parsed.bozo and not entries:
        out["rss_status"] = "error"
        out["rss_error"] = str(getattr(parsed, "bozo_exception", "bozo"))[:200]
        return out

    latest = None
    recent = 0
    undated = 0
    for e in entries:
        t = parse_published(e)
        if t is None:
            undated += 1
            recent += 1  # fetch_news 對無時間項目會保留
            continue
        if latest is None or t > latest:
            latest = t
        if t >= cutoff:
            recent += 1

    out["rss_items_48h"] = recent
    out["rss_latest_at"] = latest.isoformat() if latest else None
    out["rss_undated"] = undated

    if recent > 0:
        out["rss_status"] = "ok"
    elif entries and latest and latest < cutoff:
        out["rss_status"] = "stale"
    elif not entries:
        out["rss_status"] = "empty"
    else:
        out["rss_status"] = "empty"
    return out


def load_readwise_feed(cutoff: datetime) -> list:
    """一次拉 Reader feed（分頁），回傳精簡 dict 列表。"""
    updated_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    docs = []
    cursor = None
    pages = 0
    max_pages = 40
    while pages < max_pages:
        cmd = [
            "readwise",
            "reader-list-documents",
            "--location",
            "feed",
            "--updated-after",
            updated_after,
            "--limit",
            "100",
            "--response-fields",
            "title,source_url,site_name,category,author,saved_at,created_at",
            "--json",
        ]
        if cursor:
            cmd += ["--page-cursor", cursor]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except FileNotFoundError:
            raise RuntimeError("readwise CLI not found on PATH")
        except subprocess.TimeoutExpired:
            raise RuntimeError("readwise CLI timed out")
        if p.returncode != 0:
            err = (p.stderr or p.stdout or "").strip()[:300]
            if pages == 0:
                raise RuntimeError(f"readwise CLI failed: {err}")
            break
        data = json.loads(p.stdout)
        results = data.get("results") or []
        if not results:
            break
        for r in results:
            src = r.get("source_url") or ""
            docs.append(
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "site_name": (r.get("site_name") or "").strip(),
                    "domain": domain_of(src),
                    "source_url": src,
                    "category": r.get("category"),
                    "author": r.get("author"),
                }
            )
        pages += 1
        cursor = data.get("nextPageCursor")
        if not cursor:
            break
    return docs


def match_readwise(docs: list, match: dict) -> list:
    domains = {d.lower() for d in (match.get("domains") or []) if d}
    sites = {s.lower() for s in (match.get("site_names") or []) if s}
    if not domains and not sites:
        return []
    hits = []
    for d in docs:
        sn = (d.get("site_name") or "").lower()
        dom = (d.get("domain") or "").lower()
        ok = False
        if sn and sn in sites:
            ok = True
        if dom and (dom in domains or any(dom.endswith("." + x) or dom == x for x in domains)):
            ok = True
        # partial: site_name equals domain key
        if not ok and sn and any(sn == x or sn.endswith(x) for x in domains):
            ok = True
        if ok:
            hits.append(d)
    return hits


def verdict_for(rss: dict, rw_count: int, match: dict) -> str:
    status = rss.get("rss_status")
    n = rss.get("rss_items_48h") or 0
    has_match_keys = bool(match.get("domains") or match.get("site_names"))
    if n > 0 and rw_count > 0:
        return "rss_ok_readwise_too"
    if n > 0:
        return "healthy"
    # RSS weak
    if rw_count > 0:
        return "use_readwise_fallback"
    if status in ("error", "empty", "stale", "no_url"):
        if not has_match_keys:
            return "fix_rss_url"
        return "subscribe_in_readwise"
    return "subscribe_in_readwise"


def audit(feeds=FEEDS, lookback_hours=LOOKBACK_HOURS) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    rw_error = None
    try:
        docs = load_readwise_feed(cutoff)
    except Exception as e:
        docs = []
        rw_error = str(e)

    rows = []
    for feed in feeds:
        match = guess_match(feed)
        rss = probe_rss(feed, cutoff)
        hits = match_readwise(docs, match) if docs else []
        v = verdict_for(rss, len(hits), match)
        if rw_error and v in ("subscribe_in_readwise", "use_readwise_fallback"):
            # can't trust readwise side
            if (rss.get("rss_items_48h") or 0) > 0:
                v = "healthy"
            else:
                v = "fix_rss_url" if rss.get("rss_status") != "ok" else v
        rows.append(
            {
                "name": feed["name"],
                "scope": feed["scope"],
                "url": feed.get("url"),
                "digest": bool(feed.get("digest")),
                "readwise_match": match,
                **rss,
                "readwise_items_48h": len(hits),
                "readwise_sample_titles": [h.get("title") for h in hits[:3]],
                "verdict": v if not rw_error else (
                    "healthy" if (rss.get("rss_items_48h") or 0) > 0
                    else ("rss_degraded_rw_unavailable" if rw_error else v)
                ),
            }
        )
        # restore proper verdict when rw ok
        if not rw_error:
            rows[-1]["verdict"] = v

    summary = {
        "lookback_hours": lookback_hours,
        "cutoff": cutoff.isoformat(),
        "feed_count": len(rows),
        "readwise_docs": len(docs),
        "readwise_error": rw_error,
        "by_verdict": {},
    }
    for r in rows:
        summary["by_verdict"][r["verdict"]] = summary["by_verdict"].get(r["verdict"], 0) + 1

    return {"summary": summary, "feeds": rows}


def print_table(report: dict) -> None:
    s = report["summary"]
    print(f"cutoff={s['cutoff']}  FEEDS={s['feed_count']}  "
          f"readwise_docs={s['readwise_docs']}  err={s.get('readwise_error')}")
    print(f"by_verdict: {s['by_verdict']}")
    print()
    hdr = f"{'name':28} {'scope':6} {'rss':8} {'48h':>4} {'rw':>4}  verdict"
    print(hdr)
    print("-" * len(hdr))
    for r in report["feeds"]:
        print(
            f"{r['name'][:28]:28} {r['scope']:6} {r['rss_status']:8} "
            f"{r['rss_items_48h']:4d} {r['readwise_items_48h']:4d}  {r['verdict']}"
        )
    print()
    fb = [r for r in report["feeds"] if r["verdict"] == "use_readwise_fallback"]
    if fb:
        print("→ 建議啟用 Readwise fallback：")
        for r in fb:
            print(f"  - {r['name']}: match={r['readwise_match']} sample={r['readwise_sample_titles'][:2]}")
    sub = [r for r in report["feeds"] if r["verdict"] == "subscribe_in_readwise"]
    if sub:
        print("→ RSS 弱且 Reader 無對應（修 RSS 或先訂閱）：")
        for r in sub:
            print(f"  - {r['name']}: rss={r['rss_status']} err={r.get('rss_error')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit FEEDS vs Readwise coverage")
    ap.add_argument("--json", dest="json_path", default=None, help="Write full report JSON")
    ap.add_argument("--lookback-hours", type=int, default=LOOKBACK_HOURS)
    args = ap.parse_args(argv)

    report = audit(lookback_hours=args.lookback_hours)
    print_table(report)
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {path}")
    # non-zero if any degraded needing action
    action = {"use_readwise_fallback", "subscribe_in_readwise", "fix_rss_url", "rss_degraded_rw_unavailable"}
    if any(r["verdict"] in action for r in report["feeds"]):
        return 0  # informational; don't fail CI by default
    return 0


if __name__ == "__main__":
    sys.exit(main())
