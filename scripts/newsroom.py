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
