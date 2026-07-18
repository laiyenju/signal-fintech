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
