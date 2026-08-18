import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))
from newsroom import source_activity, build_run, append_run

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
    assert got["A"]["status"] == "active_rss"
    assert got["Silent"]["windowItems"] == 0     # 沒更新的源仍列出
    assert got["Silent"]["contributed"] == 0
    assert got["Silent"]["status"] == "silent"


def test_source_activity_marks_readwise_only_active():
    feeds = [{"name": "CoinDesk", "scope": "global"}]
    raw = [{"source": "CoinDesk", "scope": "global", "via": "readwise"}]
    meta = {"tw": {"scoredPool": []}, "global": {"scoredPool": []}}
    got = source_activity(raw, meta, feeds)[0]
    assert got["windowItems"] == 1
    assert got["viaReadwise"] == 1
    assert got["viaRss"] == 0
    assert got["status"] == "active_readwise"


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


def test_render_markdown_contains_key_facts():
    from newsroom import render_markdown
    day = {"date": "2026-07-18", "runs": [{
        "runAt": "2026-07-18T05:00:00Z", "outcome": "published", "notes": "重點在支付",
        "sources": [{"name": "A", "scope": "tw", "windowItems": 6, "contributed": 1},
                    {"name": "靜默源", "scope": "tw", "windowItems": 0, "contributed": 0}],
        "tw": {"cover": {"tier": "top", "headline": "支付大新聞", "eventKey": "e1"},
               "scoredPool": [
                   {"eventKey": "e1", "source": "A", "class": "A", "impact": 4, "volume": 3,
                    "score": 3.6, "decision": "cover", "reason": "最高分 A"},
                   {"eventKey": "e2", "source": "A", "class": "B", "impact": 2, "volume": 2,
                    "score": 2.1, "decision": "dropped", "reason": "未達 2.5"},
                   {"eventKey": "e3", "source": "B", "class": "C", "score": None,
                    "decision": "dropped", "reason": "C 類淘汰"}],
               "rejectedSummary": {"total": 10, "eligible": 2, "ineligible": 8}},
        "global": {"cover": {"tier": "watch", "headline": None, "eventKey": None},
                   "scoredPool": [], "rejectedSummary": {"total": 3, "eligible": 0, "ineligible": 3}}}]}
    md = render_markdown(day)
    assert "# 2026-07-18 選稿日誌" in md
    assert "本日一覽" in md
    assert "| published | 1 |" in md
    assert "05:00 UTC / 13:00 台北" in md and "published" in md
    assert "支付大新聞" in md
    assert "`e1`" in md
    # cover + funnel table
    assert "| Scope | 頭條 | tier | eventKey | 候選 | 合格 |" in md
    assert "| TW | 支付大新聞 | top | `e1` | 10 | 2 |" in md
    assert "| Global | — | watch | — | 3 | 0 |" in md
    # sources table (single combined)
    assert "| 類型 | 源 | 視窗條數 / 貢獻 |" in md
    assert "| 最活躍 | A | window=6 |" in md
    assert "| 靜默（前3） | 靜默源 | 0 |" in md
    assert "| 有貢獻 | A | contributed=1 |" in md
    # decision table, reason last col; score None → —
    assert "| 決策 | eventKey | class | impact | volume | score | source | reason |" in md
    assert "| ✅ cover | `e1` | A | 4 | 3 | 3.6 | A | 最高分 A |" in md
    assert "| ✗ dropped | `e3` | C | — | — | — | B | C 類淘汰 |" in md
    assert "None" not in md
    assert "未達 2.5" in md
    assert "<details><summary>編輯註記</summary>" in md
    assert "重點在支付" in md


def test_render_markdown_silent_names_capped_at_three():
    from newsroom import render_markdown
    silent = [f"S{i}" for i in range(5)]
    day = {"date": "2026-07-18", "runs": [{
        "runAt": "2026-07-18T05:00:00Z", "outcome": "no_change", "notes": "",
        "sources": (
            [{"name": "Hot", "scope": "tw", "windowItems": 9, "contributed": 0}]
            + [{"name": n, "scope": "tw", "windowItems": 0, "contributed": 0} for n in silent]),
        "tw": {"cover": {"tier": "watch", "headline": "h", "eventKey": None},
               "scoredPool": [], "rejectedSummary": {}},
        "global": {"cover": {"tier": "watch", "headline": "g", "eventKey": None},
                   "scoredPool": [], "rejectedSummary": {}}}]}
    md = render_markdown(day)
    assert "共 6 源、靜默 5 源" in md
    assert "| 靜默（前3） | S0 | 0 |" in md
    assert "| 靜默（前3） | S1 | 0 |" in md
    assert "| 靜默（前3） | S2 | 0 |" in md
    assert "| 靜默（其餘） | 等 2 源 | 0 |" in md
    assert "S3" not in md and "S4" not in md
    assert "| 有貢獻 | — | 無源貢獻進稿 |" in md
    assert "| no_change | 1 |" in md


def test_render_markdown_footer_stamp():
    from newsroom import render_markdown
    day = {"date": "2026-07-18", "runs": [
        {"runAt": "2026-07-18T05:00:00Z", "outcome": "no_change", "notes": "", "sources": [],
         "tw": {"cover": {}, "scoredPool": [], "rejectedSummary": {}},
         "global": {"cover": {}, "scoredPool": [], "rejectedSummary": {}}},
        {"runAt": "2026-07-18T23:50:00Z", "outcome": "published", "notes": "", "sources": [],
         "tw": {"cover": {}, "scoredPool": [], "rejectedSummary": {}},
         "global": {"cover": {}, "scoredPool": [], "rejectedSummary": {}}}]}
    md = render_markdown(day)
    # 頁尾用最後一輪的 runAt，UTC 與台北並列
    assert "_本頁最後更新：2026-07-18 23:50 UTC／07:50 台北（共 2 輪）_" in md


def _write_day(base, date, run_ats):
    day = {"date": date, "runs": [
        {"runAt": ra, "outcome": "published", "notes": "", "sources": [],
         "tw": {"cover": {}, "scoredPool": [], "rejectedSummary": {}},
         "global": {"cover": {}, "scoredPool": [], "rejectedSummary": {}}}
        for ra in run_ats]}
    with open(os.path.join(base, date + ".json"), "w", encoding="utf-8") as f:
        json.dump(day, f, ensure_ascii=False)
    return day


def test_update_wiki_index_generates_home_and_sidebar():
    from newsroom import update_wiki_index
    d = tempfile.mkdtemp()
    try:
        _write_day(d, "2026-07-19", ["2026-07-19T05:00:00Z"])
        _write_day(d, "2026-07-24", ["2026-07-24T02:00:00Z", "2026-07-24T05:00:00Z"])
        update_wiki_index(d)
        home = open(os.path.join(d, "Home.md"), encoding="utf-8").read()
        side = open(os.path.join(d, "_Sidebar.md"), encoding="utf-8").read()
        assert "## 最近日誌" in home
        assert "- [2026-07-24](2026-07-24)" in home
        assert "- [2026-07-19](2026-07-19)" in home
        # 新到舊
        assert home.index("2026-07-24") < home.index("2026-07-19")
        # 缺日標記（07-20 ～ 07-23）與最後更新時間（取最新日最後一輪）
        assert "缺 2026-07-20 ～ 2026-07-23" in home
        assert "最後更新：2026-07-24 05:00 UTC／13:00 台北" in home
        assert "- [2026-07-24](2026-07-24)" in side
        assert "- [Home](Home)" in side
    finally:
        shutil.rmtree(d)


def test_update_wiki_index_preserves_handwritten_home_sections():
    from newsroom import update_wiki_index
    d = tempfile.mkdtemp()
    try:
        _write_day(d, "2026-08-01", ["2026-08-01T00:50:00Z"])
        with open(os.path.join(d, "Home.md"), "w", encoding="utf-8") as f:
            f.write("# SIGNAL 選稿日誌（Newsroom）\n\n開場白。\n\n"
                    "## 最近日誌\n\n- [2026-07-24](2026-07-24)\n\n"
                    "## Outcome 圖例\n\n手寫表格。\n")
        update_wiki_index(d)
        home = open(os.path.join(d, "Home.md"), encoding="utf-8").read()
        assert "開場白。" in home and "手寫表格。" in home     # 手寫段落保留
        assert "- [2026-08-01](2026-08-01)" in home           # 索引換成實際檔案清單
        assert "- [2026-07-24](2026-07-24)" not in home       # 舊的手寫清單被取代
        # 再跑一次要冪等（marker 已埋入）
        update_wiki_index(d)
        assert home == open(os.path.join(d, "Home.md"), encoding="utf-8").read()
    finally:
        shutil.rmtree(d)


def test_merge_backup_appends_missing_runs_and_rerenders():
    from newsroom import merge_backup
    wiki = tempfile.mkdtemp()
    backup = tempfile.mkdtemp()
    try:
        _write_day(wiki, "2026-08-01", ["2026-08-01T00:50:00Z"])
        # 備援有同一天的另一輪 + wiki 沒有的一天
        _write_day(backup, "2026-08-01", ["2026-08-01T00:50:00Z", "2026-08-01T03:50:00Z"])
        _write_day(backup, "2026-08-02", ["2026-08-02T00:50:00Z"])
        assert merge_backup(backup, wiki) == 0
        day1 = json.load(open(os.path.join(wiki, "2026-08-01.json"), encoding="utf-8"))
        assert [r["runAt"] for r in day1["runs"]] == \
               ["2026-08-01T00:50:00Z", "2026-08-01T03:50:00Z"]   # 去重 append
        assert os.path.exists(os.path.join(wiki, "2026-08-02.md"))
        home = open(os.path.join(wiki, "Home.md"), encoding="utf-8").read()
        assert "- [2026-08-02](2026-08-02)" in home
    finally:
        shutil.rmtree(wiki)
        shutil.rmtree(backup)


def test_render_only_rewrites_md_from_json():
    from newsroom import render_only, render_markdown
    d = tempfile.mkdtemp()
    try:
        day = {"date": "2026-07-19", "runs": [{
            "runAt": "2026-07-19T00:00:00Z", "outcome": "published", "notes": "n",
            "sources": [],
            "tw": {"cover": {"tier": "top", "headline": "回填頭條", "eventKey": "k"},
                   "scoredPool": [], "rejectedSummary": {"total": 1, "eligible": 1}},
            "global": {"cover": {"tier": "watch", "headline": "g", "eventKey": None},
                       "scoredPool": [], "rejectedSummary": {}}}]}
        jp = os.path.join(d, "2026-07-19.json")
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(day, f, ensure_ascii=False)
        assert render_only(jp) == 0
        mp = os.path.join(d, "2026-07-19.md")
        assert os.path.exists(mp)
        assert open(mp, encoding="utf-8").read() == render_markdown(day)
        assert "回填頭條" in open(mp, encoding="utf-8").read()
    finally:
        shutil.rmtree(d)
