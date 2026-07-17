import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from validate import validate

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

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print("ALL PASS")
