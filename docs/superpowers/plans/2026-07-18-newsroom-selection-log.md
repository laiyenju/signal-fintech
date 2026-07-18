# Newsroom 選稿日誌 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每輪選稿留下可回溯的結構化紀錄與一份可讀的每日編輯室日記，並記錄各資料源更新量作為汰換依據。

**Architecture:** LLM 只產出擴充版 `candidate.meta.json`（加 `scoredPool`/`rejectedSummary`/`runAt`/`outcome`/`notes`，不動 `validate.py` 吃的 `newItems`/`today`）。新腳本 `scripts/newsroom.py` 確定性地：以 `scripts/feeds.py` 的完整名冊算各源更新量、append 一筆 run 進 `newsroom/<日期>.json`、由該 json 完整重繪 `newsroom/<日期>.md`。排程指令在每輪結束前（含無變化、fail-safe）呼叫一次並提交。

**Tech Stack:** Python 3 標準庫（零依賴，與 `validate.py`/`test_validate.py` 一致，pytest 風格測試）。

## Global Constraints

- **零第三方依賴**：`feeds.py`、`newsroom.py` 及其測試只用標準庫（不得 import feedparser）。
- **不得破壞 `validate.py` 契約**：`candidate.meta.json` 的 `today` 與 `meta[scope].newItems`（欄位 `eventKey/role/class/impact/score/isCrypto`）維持原樣；新欄位一律新增。
- **`scoredPool[].source`** = raw_items 裡的來源 feed 名（TLDR 拆出者記為 `"TLDR Fintech"` 等 feed 名），用於汰換歸因，非對外媒體標示。
- **`today`** 用台北時區日界（`TZ=Asia/Taipei date +%Y-%m-%d`），由 meta 帶入。
- **測試檔**放 `scripts/`，命名 `test_*.py`，pytest 可跑；`newsroom.py` 另含 `__main__` 內 `demo()` 自我檢查（無參數時執行）。
- **git commit 訊息**結尾加空行後 `Co-authored-by: Grok <grok@x.ai>`。

---

### Task 1: 抽出 `scripts/feeds.py` 名冊，rewire fetch_news.py

**Files:**
- Create: `scripts/feeds.py`
- Modify: `scripts/fetch_news.py:29-59`（把 inline `FEEDS = [...]` 換成 import）
- Test: `scripts/test_feeds.py`

**Interfaces:**
- Produces: `feeds.FEEDS` — `list[dict]`，每項 `{"name": str, "scope": "tw"|"global", "url": str, "digest"?: bool}`。後續 Task 2/5 以 `name`+`scope` 為名冊。

- [ ] **Step 1: 建立 `scripts/feeds.py`（把現有 FEEDS 原封搬過來）**

```python
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
```

- [ ] **Step 2: 寫測試 `scripts/test_feeds.py`（維持零依賴，不 import fetch_news／feedparser）**

```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from feeds import FEEDS

def test_feeds_shape():
    assert len(FEEDS) == 22
    names = [f["name"] for f in FEEDS]
    assert len(set(names)) == len(names)          # 無重複來源名
    for f in FEEDS:
        assert set(("name", "scope", "url")).issubset(f)
        assert f["scope"] in ("tw", "global")
```

（fetch_news 是否確實改用共用名冊，由 Step 6 冒煙驗證——那步本來就需要 feedparser，不併入零依賴的 pytest。）

- [ ] **Step 3: 跑測試確認通過**

Run: `cd scripts && python -m pytest test_feeds.py -v`
Expected: PASS（1 passed）— Step 1 已建好 feeds.py，本測試即綠

- [ ] **Step 4: 修改 `scripts/fetch_news.py`——把 inline FEEDS 換成 import**

刪掉 `fetch_news.py:24-59`（`# ---` 名冊註解 + 整個 `FEEDS = [...]` 區塊），改成：

```python
from feeds import FEEDS  # 資料源名冊（單一事實來源，見 feeds.py）
```

放在檔案上方 import 區（緊接 `import feedparser` 之後）。其餘程式不動。

- [ ] **Step 5: 跑測試確認仍通過**

Run: `cd scripts && python -m pytest test_feeds.py -v`
Expected: PASS（1 passed）

- [ ] **Step 6: 冒煙——確認 fetcher 改用共用名冊且仍可載入**

Run: `cd scripts && python -c "import fetch_news; print(len(fetch_news.FEEDS))"`
Expected: 印出 `22`

- [ ] **Step 7: Commit**

```bash
git add scripts/feeds.py scripts/fetch_news.py scripts/test_feeds.py
git commit -m "refactor: 抽出 feeds.py 名冊，fetch_news 改為 import

Co-authored-by: Grok <grok@x.ai>"
```

---

### Task 2: `source_activity()` — 各資料源更新量（含靜默源）

**Files:**
- Create: `scripts/newsroom.py`
- Test: `scripts/test_newsroom.py`

**Interfaces:**
- Consumes: `feeds.FEEDS`（Task 1）。
- Produces: `source_activity(raw_items, meta, feeds=FEEDS) -> list[dict]`，每項 `{"name","scope","windowItems","contributed"}`，依 `(scope, name)` 排序。`windowItems` = raw_items 中同名同 scope 的則數；`contributed` = meta 兩 scope 的 `scoredPool` 中 `source==name 且 decision != "dropped"` 的則數。

- [ ] **Step 1: 寫失敗測試（新增到 `scripts/test_newsroom.py`）**

```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from newsroom import source_activity

def test_source_activity_counts_silent_and_dropped():
    feeds = [{"name": "A", "scope": "tw"}, {"name": "Silent", "scope": "tw"}]
    raw = [{"source": "A", "scope": "tw"}, {"source": "A", "scope": "tw"}]
    meta = {"tw": {"scoredPool": [
                {"source": "A", "decision": "cover"},
                {"source": "A", "decision": "dropped"}]},
            "global": {"scoredPool": []}}
    got = {s["name"]: s for s in source_activity(raw, meta, feeds)}
    assert got["A"]["windowItems"] == 2
    assert got["A"]["contributed"] == 1          # dropped 不算
    assert got["Silent"]["windowItems"] == 0     # 沒更新的源仍列出
    assert got["Silent"]["contributed"] == 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd scripts && python -m pytest test_newsroom.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'newsroom'`）

- [ ] **Step 3: 建立 `scripts/newsroom.py` 並實作 `source_activity`**

```python
"""SIGNAL Newsroom 選稿日誌產生器。零依賴，標準庫 only。
用法（排程任務每輪呼叫一次）：
    python scripts/newsroom.py candidate.meta.json candidate.json scripts/raw_items.json <outcome>
    <outcome> = published | no_change | fail_safe
輸出：newsroom/<today>.json（append 一筆 run）與 newsroom/<today>.md（完整重繪）。"""
import json, os, sys
from collections import Counter
from feeds import FEEDS

DECISION_LABEL = {"cover": "✅ cover", "others": "▫️ others",
                  "context": "➕ context", "dropped": "✗ dropped"}


def source_activity(raw_items, meta, feeds=FEEDS):
    window = Counter((it.get("source"), it.get("scope"))
                     for it in raw_items if isinstance(it, dict))
    contrib = Counter()
    for scope in ("tw", "global"):
        pool = (meta.get(scope) or {}).get("scoredPool") or []
        for e in pool:
            if isinstance(e, dict) and e.get("decision") != "dropped":
                contrib[e.get("source")] += 1
    out = [{"name": f["name"], "scope": f["scope"],
            "windowItems": window.get((f["name"], f["scope"]), 0),
            "contributed": contrib.get(f["name"], 0)} for f in feeds]
    out.sort(key=lambda s: (s["scope"], s["name"]))
    return out
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd scripts && python -m pytest test_newsroom.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/newsroom.py scripts/test_newsroom.py
git commit -m "feat: newsroom source_activity（含靜默源與 contributed）

Co-authored-by: Grok <grok@x.ai>"
```

---

### Task 3: `build_run()` — 由 meta+candidate 組出一筆 run

**Files:**
- Modify: `scripts/newsroom.py`
- Test: `scripts/test_newsroom.py`

**Interfaces:**
- Consumes: `source_activity`（Task 2）。
- Produces: `build_run(meta, candidate, raw_items, feeds=FEEDS) -> dict`，結構：
  `{"runAt", "outcome", "notes", "sources": [...], "tw": {...}, "global": {...}}`，其中每 scope
  `{"cover": {"tier","headline","eventKey"}, "scoredPool": [...], "rejectedSummary": {...}}`。
  `headline` 取 `candidate[scope].cover.title`；`eventKey` 取 scoredPool 中 `decision=="cover"` 的首筆。

- [ ] **Step 1: 寫失敗測試（新增到 `scripts/test_newsroom.py`）**

```python
from newsroom import build_run

def _meta():
    return {"today": "2026-07-18", "runAt": "2026-07-18T05:00:00Z",
            "outcome": "published", "notes": "本輪重點在支付",
            "tw": {"newItems": [], "scoredPool": [
                {"eventKey": "e1", "source": "A", "score": 3.6, "decision": "cover", "reason": "最高分 A"},
                {"eventKey": "e2", "source": "A", "score": 2.1, "decision": "dropped", "reason": "未達 2.5"}],
                "rejectedSummary": {"total": 10, "eligible": 2, "ineligible": 8}},
            "global": {"newItems": [], "scoredPool": []}}

def test_build_run_shape():
    cand = {"tw": {"cover": {"tier": "top", "title": "支付大新聞"}},
            "global": {"cover": {"tier": "watch", "title": "g"}}}
    run = build_run(_meta(), cand, [{"source": "A", "scope": "tw"}])
    assert run["runAt"] == "2026-07-18T05:00:00Z"
    assert run["notes"] == "本輪重點在支付"
    assert run["tw"]["cover"] == {"tier": "top", "headline": "支付大新聞", "eventKey": "e1"}
    assert len(run["tw"]["scoredPool"]) == 2
    assert run["tw"]["rejectedSummary"]["eligible"] == 2
    assert isinstance(run["sources"], list)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd scripts && python -m pytest test_newsroom.py::test_build_run_shape -v`
Expected: FAIL（`cannot import name 'build_run'`）

- [ ] **Step 3: 在 `newsroom.py` 加入 `build_run` 與 helper**

```python
def _cover_key(scope_meta):
    for e in (scope_meta.get("scoredPool") or []):
        if isinstance(e, dict) and e.get("decision") == "cover":
            return e.get("eventKey")
    return None


def build_run(meta, candidate, raw_items, feeds=FEEDS):
    run = {"runAt": meta.get("runAt"), "outcome": meta.get("outcome"),
           "notes": meta.get("notes", "") or "",
           "sources": source_activity(raw_items, meta, feeds)}
    cand = candidate if isinstance(candidate, dict) else {}
    for scope in ("tw", "global"):
        m = meta.get(scope) or {}
        cover = (cand.get(scope) or {}).get("cover") or {}
        run[scope] = {
            "cover": {"tier": cover.get("tier"),
                      "headline": cover.get("title"),
                      "eventKey": _cover_key(m)},
            "scoredPool": m.get("scoredPool") or [],
            "rejectedSummary": m.get("rejectedSummary") or {}}
    return run
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd scripts && python -m pytest test_newsroom.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/newsroom.py scripts/test_newsroom.py
git commit -m "feat: newsroom build_run 組出單輪紀錄

Co-authored-by: Grok <grok@x.ai>"
```

---

### Task 4: `append_run()` — 冪等寫入當日 json

**Files:**
- Modify: `scripts/newsroom.py`
- Test: `scripts/test_newsroom.py`

**Interfaces:**
- Produces: `append_run(day_path, run, date) -> dict`。若 `day_path` 存在則載入、否則建 `{"date": date, "runs": []}`；以 `runAt` 為 key 先移除同 key 舊筆再 append（冪等），依 `runAt` 升冪排序，寫回檔案並回傳整個 day dict。

- [ ] **Step 1: 寫失敗測試（新增到 `scripts/test_newsroom.py`）**

```python
import json, tempfile, shutil
from newsroom import append_run

def test_append_run_idempotent_and_sorted():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "2026-07-18.json")
        r1 = {"runAt": "2026-07-18T08:00:00Z", "outcome": "published"}
        r0 = {"runAt": "2026-07-18T05:00:00Z", "outcome": "no_change"}
        append_run(p, r1, "2026-07-18")
        append_run(p, r0, "2026-07-18")           # 較早時戳，應排在前
        day = append_run(p, dict(r1, outcome="fail_safe"), "2026-07-18")  # 同 runAt → 取代非新增
        assert day["date"] == "2026-07-18"
        assert [r["runAt"] for r in day["runs"]] == \
               ["2026-07-18T05:00:00Z", "2026-07-18T08:00:00Z"]
        assert day["runs"][1]["outcome"] == "fail_safe"   # 被取代
        on_disk = json.load(open(p, encoding="utf-8"))
        assert on_disk == day
    finally:
        shutil.rmtree(d)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd scripts && python -m pytest test_newsroom.py::test_append_run_idempotent_and_sorted -v`
Expected: FAIL（`cannot import name 'append_run'`）

- [ ] **Step 3: 在 `newsroom.py` 加入 `append_run`**

```python
def append_run(day_path, run, date):
    if os.path.exists(day_path):
        with open(day_path, encoding="utf-8") as f:
            day = json.load(f)
        if not isinstance(day, dict):
            day = {}
    else:
        day = {}
    day["date"] = date
    runs = [r for r in day.get("runs", [])
            if isinstance(r, dict) and r.get("runAt") != run.get("runAt")]
    runs.append(run)
    runs.sort(key=lambda r: r.get("runAt") or "")
    day["runs"] = runs
    with open(day_path, "w", encoding="utf-8") as f:
        json.dump(day, f, ensure_ascii=False, indent=2)
    return day
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd scripts && python -m pytest test_newsroom.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/newsroom.py scripts/test_newsroom.py
git commit -m "feat: newsroom append_run 冪等寫入當日 json

Co-authored-by: Grok <grok@x.ai>"
```

---

### Task 5: `render_markdown()` — 由當日 json 重繪日記

**Files:**
- Modify: `scripts/newsroom.py`
- Test: `scripts/test_newsroom.py`

**Interfaces:**
- Produces: `render_markdown(day) -> str`。每筆 run 一區塊：`## HH:MM UTC（outcome）`、TW/Global 頭條（headline＋tier）、資料源動態（總數／靜默源名單／前三活躍源）、每 scope 的編輯決策清單（decision 標籤＋eventKey＋score＋reason）、可選編輯註記。

- [ ] **Step 1: 寫失敗測試（新增到 `scripts/test_newsroom.py`）**

```python
from newsroom import render_markdown

def test_render_markdown_contains_key_facts():
    day = {"date": "2026-07-18", "runs": [{
        "runAt": "2026-07-18T05:00:00Z", "outcome": "published", "notes": "重點在支付",
        "sources": [{"name": "A", "scope": "tw", "windowItems": 6, "contributed": 1},
                    {"name": "靜默源", "scope": "tw", "windowItems": 0, "contributed": 0}],
        "tw": {"cover": {"tier": "top", "headline": "支付大新聞", "eventKey": "e1"},
               "scoredPool": [{"eventKey": "e1", "score": 3.6, "decision": "cover", "reason": "最高分 A"},
                              {"eventKey": "e2", "score": 2.1, "decision": "dropped", "reason": "未達 2.5"}],
               "rejectedSummary": {}},
        "global": {"cover": {"tier": "watch", "headline": None, "eventKey": None},
                   "scoredPool": [], "rejectedSummary": {}}}]}
    md = render_markdown(day)
    assert "# 2026-07-18 選稿日誌" in md
    assert "05:00 UTC" in md and "published" in md
    assert "支付大新聞" in md            # 頭條
    assert "靜默源" in md                # 靜默源被點名
    assert "e2" in md and "未達 2.5" in md  # 落選項與理由都在
    assert "重點在支付" in md            # 編輯註記
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd scripts && python -m pytest test_newsroom.py::test_render_markdown_contains_key_facts -v`
Expected: FAIL（`cannot import name 'render_markdown'`）

- [ ] **Step 3: 在 `newsroom.py` 加入 `render_markdown`**

```python
def render_markdown(day):
    lines = [f"# {day.get('date')} 選稿日誌", ""]
    for run in day.get("runs", []):
        hhmm = (run.get("runAt") or "")[11:16]
        lines.append(f"## {hhmm} UTC（{run.get('outcome')}）")
        for scope, label in (("tw", "TW"), ("global", "Global")):
            cover = (run.get(scope) or {}).get("cover") or {}
            lines.append(f"**{label} 頭條**：{cover.get('headline') or '—'}"
                         f"（{cover.get('tier') or '—'}）")
        srcs = run.get("sources", [])
        silent = [s["name"] for s in srcs if not s.get("windowItems")]
        active = sorted((s for s in srcs if s.get("windowItems")),
                        key=lambda s: -s["windowItems"])[:3]
        lines.append("")
        note = f"（{'、'.join(silent)}）" if silent else ""
        lines.append(f"**資料源動態**：{len(srcs)} 源、{len(silent)} 源靜默{note}。")
        if active:
            lines.append("最活躍：" +
                         "、".join(f"{s['name']}({s['windowItems']})" for s in active) + "。")
        for scope, label in (("tw", "TW"), ("global", "Global")):
            pool = (run.get(scope) or {}).get("scoredPool") or []
            if not pool:
                continue
            lines += ["", f"**編輯決策（{label}）**"]
            for e in pool:
                tag = DECISION_LABEL.get(e.get("decision"), e.get("decision"))
                lines.append(f"- {tag}　{e.get('eventKey')} score {e.get('score')}"
                             f" — {e.get('reason', '')}")
        if run.get("notes"):
            lines += ["", f"_編輯註記：{run['notes']}_"]
        lines += ["", "---", ""]
    return "\n".join(lines)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd scripts && python -m pytest test_newsroom.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add scripts/newsroom.py scripts/test_newsroom.py
git commit -m "feat: newsroom render_markdown 重繪日記

Co-authored-by: Grok <grok@x.ai>"
```

---

### Task 6: `main()` CLI ＋ `demo()` 自我檢查

**Files:**
- Modify: `scripts/newsroom.py`

**Interfaces:**
- Consumes: `build_run`, `append_run`, `render_markdown`, `source_activity`。
- Produces: `main(argv) -> int`（argv = `[prog, meta_path, candidate_path, raw_items_path, outcome]`）。讀三個 JSON，`today = meta["today"]`，寫 `newsroom/<today>.json`（append）與 `newsroom/<today>.md`（重繪），印確認行。無參數時執行 `demo()` 自我檢查。

- [ ] **Step 1: 在 `newsroom.py` 末端加入 `main`、`demo` 與進入點**

```python
def main(argv):
    with open(argv[1], encoding="utf-8") as f:
        meta = json.load(f)
    with open(argv[2], encoding="utf-8") as f:
        candidate = json.load(f)
    with open(argv[3], encoding="utf-8") as f:
        raw_items = json.load(f)
    outcome = argv[4] if len(argv) > 4 else meta.get("outcome")
    meta["outcome"] = outcome
    today = meta.get("today")
    os.makedirs("newsroom", exist_ok=True)
    day_path = os.path.join("newsroom", f"{today}.json")
    run = build_run(meta, candidate, raw_items)
    run["outcome"] = outcome
    day = append_run(day_path, run, today)
    md_path = os.path.join("newsroom", f"{today}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(day))
    print(f"[newsroom] {today} {run.get('runAt')} ({outcome}) → {len(day['runs'])} runs, "
          f"{day_path} + {md_path}")
    return 0


def demo():
    import tempfile, shutil
    feeds = [{"name": "A", "scope": "tw"}, {"name": "Silent", "scope": "tw"}]
    raw = [{"source": "A", "scope": "tw"}]
    meta = {"today": "2026-07-18", "runAt": "2026-07-18T05:00:00Z", "outcome": "published",
            "notes": "n",
            "tw": {"newItems": [], "scoredPool": [
                {"eventKey": "e1", "source": "A", "score": 3.6, "decision": "cover", "reason": "最高分"}]},
            "global": {"newItems": [], "scoredPool": []}}
    cand = {"tw": {"cover": {"tier": "top", "title": "標題"}},
            "global": {"cover": {"tier": "watch", "title": "g"}}}
    sa = {s["name"]: (s["windowItems"], s["contributed"]) for s in source_activity(raw, meta, feeds)}
    assert sa == {"A": (1, 1), "Silent": (0, 0)}, sa
    run = build_run(meta, cand, raw, feeds)
    run["outcome"] = "published"
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "day.json")
        append_run(p, run, "2026-07-18")
        day = append_run(p, run, "2026-07-18")   # 同 runAt 不重複
        assert len(day["runs"]) == 1
        md = render_markdown(day)
        assert "標題" in md and "e1" in md and "最高分" in md
    finally:
        shutil.rmtree(d)
    print("newsroom demo OK")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main(sys.argv))
    demo()
```

- [ ] **Step 2: 跑自我檢查**

Run: `cd scripts && python newsroom.py`
Expected: 印出 `newsroom demo OK`（無 AssertionError）

- [ ] **Step 3: 端到端冒煙（用暫存假資料，驗證真的產出檔案）**

Run:
```bash
cd /Users/yenlai/Documents/signal
python - <<'PY'
import json
json.dump({"today":"2026-07-18","runAt":"2026-07-18T05:00:00Z","outcome":"published","notes":"冒煙",
  "tw":{"newItems":[],"scoredPool":[{"eventKey":"e1","source":"TechCrunch Fintech","score":3.6,"decision":"cover","reason":"最高分 A"}]},
  "global":{"newItems":[],"scoredPool":[]}}, open("candidate.meta.json","w"), ensure_ascii=False)
json.dump({"tw":{"cover":{"tier":"top","title":"冒煙頭條"}},"global":{"cover":{"tier":"watch","title":"g"}}}, open("candidate.json","w"), ensure_ascii=False)
json.dump([{"source":"TechCrunch Fintech","scope":"global"}], open("scripts/raw_items.json","w"), ensure_ascii=False)
PY
python scripts/newsroom.py candidate.meta.json candidate.json scripts/raw_items.json published
cat newsroom/2026-07-18.md
```
Expected: 印出確認行；`newsroom/2026-07-18.md` 含「冒煙頭條」與「TechCrunch Fintech」，且列出多個 tw 靜默源。

- [ ] **Step 4: 清掉冒煙產物（candidate.* 已被 gitignore，不會誤 commit）**

Run: `cd /Users/yenlai/Documents/signal && rm -f newsroom/2026-07-18.json newsroom/2026-07-18.md candidate.json candidate.meta.json scripts/raw_items.json`

- [ ] **Step 5: 跑全部測試確認沒退化**

Run: `cd scripts && python -m pytest -v`
Expected: PASS（feeds + newsroom + validate 全綠）

- [ ] **Step 6: Commit**

```bash
git add scripts/newsroom.py
git commit -m "feat: newsroom CLI main 與 demo 自我檢查

Co-authored-by: Grok <grok@x.ai>"
```

---

### Task 7: 排程指令接入 newsroom（`排程任務指令.md`）

**Files:**
- Modify: `排程任務指令.md`（第 13 步 meta 擴充；新增 13.6 節；13.3 / 13.5 / 14 三分支各呼叫一次）

**Interfaces:**
- Consumes: `scripts/newsroom.py`（Task 6 的 CLI 介面）。
- 這是文件（提示詞）改動，無 pytest；驗證以「Task 6 冒煙已證明 CLI 可用」＋「人工複讀三分支都呼叫且帶正確 outcome」為準。

- [ ] **Step 1: 擴充第 13 步的 meta 說明**

把 `排程任務指令.md:322-327`（第 13 節第 1–2 點）改寫為：

```markdown
1. 依第 6 節結構組裝完整結果，寫入 `candidate.json`（**不覆蓋** `data.json`）。
2. 同時寫出 `candidate.meta.json`。**既有欄位維持原樣**（validate.py 契約）：
   - `today`：以 `TZ=Asia/Taipei date +%Y-%m-%d` 取得。
   - 每個 scope 的 `newItems`（只列 role 為 cover/others/context 的新進內容）：
     `{eventKey, role, class, impact, volume, score, isCrypto}`。轉存與 7 天內未動的既有項目不列入。
   **本次新增以下欄位（供 newsroom 日誌，validate.py 會忽略）：**
   - `runAt`：本輪 UTC ISO 8601 時戳（與第 13 步第 4 點的 `_generated_at` 同值）。
   - `notes`：本輪整體編輯判斷，一到三句繁中（可空字串）。
   - 每個 scope 的 `scoredPool`：**所有通過 A/B 資格並被打分的候選**（含落選），每則
     `{eventKey, source, class, impact, volume, score, decision, reason}`。
     - `source`：該候選來自哪個資料源，**用 raw_items 裡的來源 feed 名**（TLDR 拆出者記 `"TLDR Fintech"` 等 feed 名），供汰換歸因。
     - `decision`：`cover` | `others` | `context` | `dropped`。
     - `reason`：一句繁中，說明為何這樣判，尤其**落選或未當 cover 的原因**。
   - 每個 scope 的 `rejectedSummary`：`{total, eligible, ineligible}`
     （total＝本輪評估的新事件數，eligible＝過資格進 scoredPool 者，ineligible＝其餘）。
```

- [ ] **Step 2: 新增「13.6 寫入 newsroom 日誌」節（放在 13.5 之後、14 之前）**

```markdown
## 13.6 寫入 newsroom 選稿日誌

**每一輪都執行一次**（含無變化、fail-safe），且**每輪僅呼叫一次**（在把關迴圈收斂之後）：

    python scripts/newsroom.py candidate.meta.json candidate.json scripts/raw_items.json <outcome>

`<outcome>` 依本輪結局擇一：`published`（第 14 步將提交）、`no_change`（第 13 步第 3 點無變化）、
`fail_safe`（13.5 滿 3 輪仍不過、保留原 data.json）。

腳本會 append 一筆 run 進 `newsroom/<today>.json` 並重繪 `newsroom/<today>.md`。
接著把這兩個檔一併提交（與 data.json 是否變動無關）：

    git add newsroom/
    git commit -m "newsroom：<today> <outcome> 選稿日誌（$(TZ=Asia/Taipei date +'%Y-%m-%d %H:%M')）"
    git push -u origin HEAD
```

- [ ] **Step 3: 在三個分支各接上 13.6**

- 第 13 步第 3 點（無變化、結束任務）之前 → 先以 `outcome=no_change` 執行 13.6 並提交推送，再結束。
- 13.5 第 5 點 fail-safe（保留原 data.json、不提交 data）→ 以 `outcome=fail_safe` 執行 13.6 並提交推送。
- 第 14 步（published）→ 先照原樣 `cp candidate.json data.json`、`git add data.json`，**同一個 commit 一併 `git add newsroom/`**（outcome=published 先跑 13.6 產檔），再 push / 建 PR / 合併。

在 `排程任務指令.md` 對應三處各加一行明確指示，指向 13.6，並標明 `<outcome>` 值。

- [ ] **Step 4: 人工複讀驗證**

Run: `grep -n "newsroom\|outcome=\|13.6" 排程任務指令.md`
Expected: 三個分支（no_change / fail_safe / published）都出現對 13.6 的呼叫且帶正確 outcome；13.6 節存在。

- [ ] **Step 5: Commit**

```bash
git add 排程任務指令.md
git commit -m "docs: 排程指令接入 newsroom 日誌（三分支每輪一次）

Co-authored-by: Grok <grok@x.ai>"
```

---

### Task 8: README 補上 newsroom

**Files:**
- Modify: `README.md`（How it works 流程圖、Repo structure、新增一段說明）

- [ ] **Step 1: 在 `README.md` 的 How it works 流程圖 `both pass -> ...` 之後加一行**

```
    -> every run (incl. no-change / fail-safe): scripts/newsroom.py appends
       newsroom/<date>.json + renders newsroom/<date>.md (selection audit log), commits it
```

- [ ] **Step 2: 在 Repo structure 區塊加入**

```
scripts/feeds.py        Canonical feed roster (imported by fetch_news + newsroom)
scripts/newsroom.py     Renders the per-run selection log
newsroom/<date>.json    Structured selection record, one entry per run (committed)
newsroom/<date>.md      Human-readable editorial diary, re-rendered each run
```

- [ ] **Step 3: 新增一小節「Selection log (newsroom)」**（放在 Editorial rules 之後）

```markdown
## Selection log (newsroom)

Every 3-hour run writes an audit trail to `newsroom/`, so the AI's picks are reviewable:

- **`newsroom/<date>.json`** — structured: for each run, per-source update counts
  (`windowItems`) and whether each source fed a selected story (`contributed`), plus the
  scored candidate pool with each item's `decision` and a one-line `reason`.
- **`newsroom/<date>.md`** — a readable editorial diary re-rendered from the JSON each run.

Logged on **every** run, including no-change and fail-safe runs. `contributed` staying 0
while `windowItems` stays high over time flags a feed worth dropping.
```

- [ ] **Step 4: 複讀確認**

Run: `grep -n "newsroom" README.md`
Expected: 流程圖、Repo structure、新小節三處都出現。

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README 補上 newsroom 選稿日誌

Co-authored-by: Grok <grok@x.ai>"
```

---

## 完成後驗收（對照 spec §12）

1. `python scripts/newsroom.py <meta> <candidate> <raw> published` → `newsroom/<today>.json` 有一筆 run，含 sources、scoredPool（含 reason）、rejectedSummary。
2. `newsroom/<today>.md` 可讀，顯示頭條、靜默源、每則決策與理由。
3. 三分支（published / no_change / fail_safe）都會寫紀錄——由 Task 7 的三處接入保證。
4. `cd scripts && python newsroom.py` → `newsroom demo OK`。
5. `cd scripts && python -m pytest -v` → feeds/newsroom/validate 全綠（meta 擴充未影響 validate）。
