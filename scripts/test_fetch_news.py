"""Unit tests for fetch helpers (no network)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fetch_news import (
    _HTTP308RedirectHandler,
    _match_doc,
    domain_of,
    needs_readwise,
    items_from_readwise,
    strip_utm,
)


def test_308_handler_exists():
    assert hasattr(_HTTP308RedirectHandler, "http_error_308")


def test_domain_of():
    assert domain_of("https://www.coindesk.com/path") == "coindesk.com"
    assert domain_of("") == ""


def test_match_doc_domain_and_site():
    match = {"domains": ["coindesk.com"], "site_names": ["coindesk.com"]}
    assert _match_doc({"site_name": "coindesk.com", "source_url": "https://x.com"}, match)
    assert _match_doc({"site_name": "", "source_url": "https://www.coindesk.com/a"}, match)
    assert not _match_doc({"site_name": "every.to", "source_url": "https://every.to/a"}, match)


def test_needs_readwise_policy():
    feed_fb = {"policy": "rss_primary_readwise_fallback", "name": "X"}
    feed_only = {"policy": "rss_only", "name": "Y"}
    assert needs_readwise(feed_fb, [], {"rss_status": "error"})
    assert needs_readwise(feed_fb, [], {"rss_status": "stale"})
    assert not needs_readwise(feed_fb, [{"title": "a"}], {"rss_status": "ok"})
    assert not needs_readwise(feed_only, [], {"rss_status": "error"})
    assert needs_readwise({"policy": "readwise_only"}, [{"x": 1}], {})


def test_items_from_readwise_filters_and_credits_feed_name():
    feed = {
        "name": "CoinDesk",
        "scope": "global",
        "readwise_match": {"domains": ["coindesk.com"], "site_names": ["coindesk.com"]},
    }
    docs = [
        {"title": "A", "source_url": "https://www.coindesk.com/a?utm_source=x",
         "site_name": "coindesk.com", "summary": "s", "saved_at": "2026-07-25T00:00:00Z"},
        {"title": "B", "source_url": "mailto:news@example.com", "site_name": "coindesk.com"},
        {"title": "C", "source_url": "https://every.to/c", "site_name": "every.to"},
    ]
    items = items_from_readwise(feed, docs)
    assert len(items) == 1
    assert items[0]["source"] == "CoinDesk"
    assert items[0]["via"] == "readwise"
    assert items[0]["link"] == strip_utm("https://www.coindesk.com/a?utm_source=x")
    assert "utm_" not in items[0]["link"]
