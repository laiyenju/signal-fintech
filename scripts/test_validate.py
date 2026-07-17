import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from validate import validate
import copy as _copy

GOOD = {
    "tw": {"cover": {"date": "2026-07-18", "tier": "top", "title": "t", "paras": ["a", "b"]},
           "sources": [], "coverSocial": [], "context": [], "others": []},
    "global": {"cover": {"date": "2026-07-18", "tier": "watch", "title": "t", "paras": ["a", "b"]},
               "sources": [], "coverSocial": [], "context": [], "others": []},
    "_generated_at": "2026-07-18T00:00:00Z",
}
GOOD_META = {"today": "2026-07-18", "tw": {"newItems": []}, "global": {"newItems": []}}
PREV = {"tw": {"cover": {"date": "2026-07-10", "tier": "top", "title": "old", "paras": ["a", "b"]},
               "sources": [], "coverSocial": [], "context": [], "others": []},
        "global": {"cover": {"date": "2026-07-10", "tier": "top", "title": "old", "paras": ["a", "b"]},
                   "sources": [], "coverSocial": [], "context": [], "others": []},
        "_generated_at": "2026-07-10T00:00:00Z"}

def rules(candidate, meta=GOOD_META, prev=PREV, today="2026-07-18"):
    return {v["rule"] for v in validate(candidate, meta, prev, today)}

def test_good_passes():
    assert validate(GOOD, GOOD_META, PREV, "2026-07-18") == []

def test_missing_toplevel_key():
    bad = {"tw": GOOD["tw"], "global": GOOD["global"]}  # 缺 _generated_at
    assert "structure.toplevel" in rules(bad)

def test_paras_not_two():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["cover"]["paras"] = ["only one"]
    assert "structure.paras" in rules(bad)

def test_bad_tier():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["cover"]["tier"] = "headline"
    assert "structure.tier" in rules(bad)

def test_array_field_null():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["sources"] = None
    assert "structure.arrays" in rules(bad)

def test_cover_not_dict():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["cover"] = None
    assert "structure.cover" in rules(bad)  # must NOT raise

def test_others_item_not_dict():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["others"] = ["not a dict"]
    assert "structure.others_item" in rules(bad)  # must NOT raise

def test_quotas_scope_not_dict():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"] = None
    meta = {"today": "2026-07-18",
            "tw": {"newItems": [{"eventKey": "e1", "role": "cover", "class": "A",
                                 "impact": 4, "volume": 3, "score": 3.6, "isCrypto": False}]},
            "global": {"newItems": []}}
    # must NOT raise; structure layer will flag the None scope, quotas must not crash
    validate(bad, meta, PREV, "2026-07-18")  # no exception = pass

def _meta(scope_items):
    return {"today": "2026-07-18", "tw": {"newItems": scope_items}, "global": {"newItems": []}}

A = {"eventKey": "e1", "role": "others", "class": "A", "impact": 3, "volume": 2, "score": 2.6, "isCrypto": False}

def test_80_20_b_over_cap():
    # N=3, B=1 → floor(3*0.2)=0 → 超標
    items = [dict(A, eventKey="e1"), dict(A, eventKey="e2"),
             dict(A, eventKey="e3", **{"class": "B"})]
    assert "quota.8020" in rules(GOOD, meta=_meta(items))

def test_80_20_ok_large_batch():
    # N=5, B=1 → floor(5*0.2)=1 → 剛好，A>=ceil(5*0.8)=4
    items = [dict(A, eventKey=f"e{i}") for i in range(4)] + [dict(A, eventKey="e5", **{"class": "B"})]
    assert "quota.8020" not in rules(GOOD, meta=_meta(items))

def test_crypto_over_two():
    items = [dict(A, eventKey=f"e{i}", isCrypto=True) for i in range(3)]  # 3 crypto others
    # N=3 全 A，80/20 過；只驗 crypto
    assert "quota.crypto" in rules(GOOD, meta=_meta(items))

def test_others_score_below_threshold():
    items = [dict(A, eventKey="e1", score=2.4)]
    assert "quota.others_score" in rules(GOOD, meta=_meta(items))

def test_b_class_as_cover():
    items = [dict(A, eventKey="e1", role="cover", **{"class": "B"})]
    assert "quota.cover_class" in rules(GOOD, meta=_meta(items))

def test_cover_top_needs_impact_3():
    # candidate.tw.cover.tier=top，但 meta cover impact=2 → 應為 watch
    items = [dict(A, eventKey="e1", role="cover", impact=2)]
    assert "quota.cover_tier" in rules(GOOD, meta=_meta(items))

def test_duplicate_eventkey_in_batch():
    items = [dict(A, eventKey="dup"), dict(A, eventKey="dup")]
    assert "quota.dup_eventkey" in rules(GOOD, meta=_meta(items))

def _others(dates):
    return [{"date": d, "title": d, "paras": ["a", "b"], "sources": [], "social": [], "context": []} for d in dates]

def test_cover_locked_changed():
    prev = _copy.deepcopy(PREV)
    prev["tw"]["cover"]["date"] = "2026-07-18"  # 今天已鎖
    prev["tw"]["cover"]["title"] = "locked"
    cand = _copy.deepcopy(GOOD)  # cover.title="t" 不同 → 違規
    assert "state.cover_locked" in rules(cand, prev=prev)

def test_others_older_than_7_days():
    cand = _copy.deepcopy(GOOD)
    cand["tw"]["others"] = _others(["2026-07-01"])  # 距 07-18 為 17 天
    assert "state.others_window" in rules(cand)

def test_others_not_sorted():
    cand = _copy.deepcopy(GOOD)
    cand["tw"]["others"] = _others(["2026-07-12", "2026-07-15"])  # 舊在前 → 未由新到舊
    assert "state.others_sorted" in rules(cand)

def test_others_count_decreased():
    prev = _copy.deepcopy(PREV)
    prev["tw"]["others"] = _others(["2026-07-15", "2026-07-14", "2026-07-13"])  # 3 則皆在窗內
    cand = _copy.deepcopy(GOOD)
    cand["tw"]["others"] = _others(["2026-07-15"])  # 剩 1 則、無過期理由 → 違規
    assert "state.others_count" in rules(cand, prev=prev)

def test_prev_cover_none_no_crash():
    import copy
    prev = copy.deepcopy(PREV)
    prev["tw"]["cover"] = None
    # must NOT raise
    validate(copy.deepcopy(GOOD), GOOD_META, prev, "2026-07-18")

def test_others_bad_date_no_crash():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["others"] = [{"date": "not-a-date", "title": "x", "paras": ["a", "b"],
                            "sources": [], "social": [], "context": []}]
    # must NOT raise
    validate(bad, GOOD_META, PREV, "2026-07-18")

def test_others_window_boundary():
    import copy
    # age exactly 7 passes, age 8 violates
    ok = copy.deepcopy(GOOD)
    ok["tw"]["others"] = [{"date": "2026-07-11", "title": "x", "paras": ["a", "b"],
                           "sources": [], "social": [], "context": []}]  # 2026-07-18 - 7d
    assert "state.others_window" not in {v["rule"] for v in validate(ok, GOOD_META, PREV, "2026-07-18")}
    bad = copy.deepcopy(GOOD)
    bad["tw"]["others"] = [{"date": "2026-07-10", "title": "x", "paras": ["a", "b"],
                            "sources": [], "social": [], "context": []}]  # 8 days
    assert "state.others_window" in {v["rule"] for v in validate(bad, GOOD_META, PREV, "2026-07-18")}

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print("ALL PASS")
