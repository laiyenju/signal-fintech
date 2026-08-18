import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from feeds import FEEDS, feed_policy, DEFAULT_POLICY

VALID_POLICIES = {"rss_only", "rss_primary_readwise_fallback", "readwise_only"}


def test_feeds_shape():
    assert len(FEEDS) == 22
    names = [f["name"] for f in FEEDS]
    assert len(set(names)) == len(names)          # 無重複來源名
    for f in FEEDS:
        assert set(("name", "scope", "url")).issubset(f)
        assert f["scope"] in ("tw", "global")
        assert feed_policy(f) in VALID_POLICIES
        if feed_policy(f) != "rss_only" or f.get("readwise_match"):
            m = f.get("readwise_match") or {}
            assert isinstance(m.get("domains", []), list)
            assert isinstance(m.get("site_names", []), list)


def test_coindesk_has_readwise_fallback():
    cd = next(f for f in FEEDS if f["name"] == "CoinDesk")
    assert feed_policy(cd) == "rss_primary_readwise_fallback"
    assert "coindesk.com" in cd["readwise_match"]["domains"]


def test_default_policy_is_readwise_fallback():
    # 雲端 egress 常 403 擋全球 RSS，預設全源開 Readwise fallback（見 feeds.py 註解）
    assert DEFAULT_POLICY == "rss_primary_readwise_fallback"
    plain = next(f for f in FEEDS if f["name"] == "Hacker News")
    assert feed_policy(plain) == "rss_primary_readwise_fallback"
    for f in FEEDS:
        if feed_policy(f) != "rss_only":
            assert f.get("readwise_match"), f["name"]  # fallback 源必須有 match 條件
