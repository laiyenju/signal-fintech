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
