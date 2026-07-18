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
    # ponytail: contrib keyed by source name only; correct because feed names are
    # globally unique (enforced by test_feeds.py). Key by (name, scope) if that changes.
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
