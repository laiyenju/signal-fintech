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
    assert got["Silent"]["windowItems"] == 0     # 沒更新的源仍列出
    assert got["Silent"]["contributed"] == 0


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
