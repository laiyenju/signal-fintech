"""SIGNAL Newsroom 選稿日誌產生器。零依賴，標準庫 only。
用法（排程任務每輪呼叫一次）：
    python scripts/newsroom.py candidate.meta.json candidate.json scripts/raw_items.json <outcome>
    <outcome> = published | no_change | fail_safe
僅重繪既有日 JSON 的 MD（不 append）：
    python scripts/newsroom.py --render-only $NEWSROOM_DIR/YYYY-MM-DD.json
輸出：$NEWSROOM_DIR/<today>.json（append 一筆 run）與 <today>.md（完整重繪）。
$NEWSROOM_DIR 預設 "newsroom"；排程時指向 wiki clone 目錄。"""
import json, os, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from feeds import FEEDS

DECISION_LABEL = {"cover": "✅ cover", "others": "▫️ others",
                  "context": "➕ context", "dropped": "✗ dropped"}
_TZ_TPE = timezone(timedelta(hours=8))
_SILENT_NAME_CAP = 3


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


def _parse_run_at(run_at):
    if not run_at or not isinstance(run_at, str):
        return None
    s = run_at.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_run_heading(run):
    run_at = run.get("runAt") or ""
    hhmm = run_at[11:16] if len(run_at) >= 16 else "—"
    outcome = run.get("outcome") or "—"
    dt = _parse_run_at(run_at)
    if dt is None:
        return f"## {hhmm} UTC（{outcome}）"
    tpe = dt.astimezone(_TZ_TPE).strftime("%H:%M")
    return f"## {hhmm} UTC / {tpe} 台北（{outcome}）"


def _format_funnel(rs):
    if not isinstance(rs, dict):
        return ""
    total, eligible = rs.get("total"), rs.get("eligible")
    if total is None and eligible is None:
        return ""
    t = total if total is not None else "—"
    e = eligible if eligible is not None else "—"
    return f"｜候選 {t} → 合格 {e}"


def _format_score(score):
    return "—" if score is None else score


def _format_decision_line(e):
    tag = DECISION_LABEL.get(e.get("decision"), e.get("decision"))
    key = e.get("eventKey") or "—"
    bits = []
    if e.get("class"):
        bits.append(f"{e['class']}類")
    if e.get("impact") is not None:
        bits.append(f"impact={e['impact']}")
    if e.get("volume") is not None:
        bits.append(f"volume={e['volume']}")
    bits.append(f"score={_format_score(e.get('score'))}")
    if e.get("source"):
        bits.append(e["source"])
    meta = " · ".join(str(b) for b in bits)
    reason = e.get("reason") or ""
    head = f"- {tag} `{key}` {meta}".rstrip()
    if reason:
        return f"{head}\n  — {reason}"
    return head


def _day_summary_lines(day):
    runs = [r for r in day.get("runs", []) if isinstance(r, dict)]
    counts = Counter(r.get("outcome") or "—" for r in runs)
    parts = [f"{k} {counts[k]}" for k in ("published", "no_change", "fail_safe") if counts.get(k)]
    extra = [f"{k} {n}" for k, n in sorted(counts.items())
             if k not in ("published", "no_change", "fail_safe")]
    parts.extend(extra)
    breakdown = "、".join(parts) if parts else "—"
    lines = ["## 本日一覽",
             f"- 輪次：{len(runs)}" + (f"（{breakdown}）" if runs else ""),
             ""]
    if runs:
        last = runs[-1]
        for scope, label in (("tw", "TW"), ("global", "Global")):
            cover = (last.get(scope) or {}).get("cover") or {}
            hl = cover.get("headline") or "—"
            tier = cover.get("tier") or "—"
            lines.append(f"- 最新 {label} 頭條：{hl}（{tier}）")
        lines.append("")
    return lines


def _silent_note(silent_names, cap=_SILENT_NAME_CAP):
    if not silent_names:
        return ""
    shown = silent_names[:cap]
    note = "、".join(shown)
    rest = len(silent_names) - len(shown)
    if rest > 0:
        note += f" 等 {rest} 源"
    return f"（{note}）"


def _contributed_line(srcs):
    contrib = sorted(
        (s for s in srcs if s.get("contributed")),
        key=lambda s: (-s.get("contributed", 0), s.get("name") or ""))
    if not contrib:
        return "本輪有貢獻：無（無源貢獻進稿）。"
    body = "、".join(f"{s['name']}({s['contributed']})" for s in contrib)
    return f"本輪有貢獻：{body}。"


def render_markdown(day):
    lines = [f"# {day.get('date')} 選稿日誌", ""]
    lines += _day_summary_lines(day)
    for run in day.get("runs", []):
        lines.append(_format_run_heading(run))
        for scope, label in (("tw", "TW"), ("global", "Global")):
            scope_data = run.get(scope) or {}
            cover = scope_data.get("cover") or {}
            funnel = _format_funnel(scope_data.get("rejectedSummary") or {})
            key = cover.get("eventKey")
            key_bit = f" · `{key}`" if key else ""
            lines.append(
                f"**{label} 頭條**：{cover.get('headline') or '—'}"
                f"（{cover.get('tier') or '—'}{key_bit}）{funnel}")
        srcs = run.get("sources", [])
        silent = [s["name"] for s in srcs if not s.get("windowItems")]
        active = sorted((s for s in srcs if s.get("windowItems")),
                        key=lambda s: -s["windowItems"])[:3]
        lines.append("")
        lines.append(
            f"**資料源動態**：{len(srcs)} 源、{len(silent)} 源靜默"
            f"{_silent_note(silent)}。")
        if active:
            lines.append("最活躍：" +
                         "、".join(f"{s['name']}({s['windowItems']})" for s in active) + "。")
        lines.append(_contributed_line(srcs))
        for scope, label in (("tw", "TW"), ("global", "Global")):
            pool = (run.get(scope) or {}).get("scoredPool") or []
            if not pool:
                continue
            lines += ["", f"**編輯決策（{label}）**"]
            for e in pool:
                lines.append(_format_decision_line(e if isinstance(e, dict) else {}))
        if run.get("notes"):
            lines += ["", f"_編輯註記：{run['notes']}_"]
        lines += ["", "---", ""]
    return "\n".join(lines)


def render_only(day_json_path):
    with open(day_json_path, encoding="utf-8") as f:
        day = json.load(f)
    md_path = os.path.splitext(day_json_path)[0] + ".md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(day))
    print(f"[newsroom] render-only → {md_path} ({len(day.get('runs') or [])} runs)")
    return 0


def main(argv):
    if len(argv) >= 3 and argv[1] == "--render-only":
        return render_only(argv[2])
    with open(argv[1], encoding="utf-8") as f:
        meta = json.load(f)
    with open(argv[2], encoding="utf-8") as f:
        candidate = json.load(f)
    with open(argv[3], encoding="utf-8") as f:
        raw_items = json.load(f)
    outcome = argv[4] if len(argv) > 4 else meta.get("outcome")
    meta["outcome"] = outcome
    today = meta.get("today")
    base = os.environ.get("NEWSROOM_DIR", "newsroom")  # 排程指向 wiki clone；本機/測試預設 newsroom
    os.makedirs(base, exist_ok=True)
    day_path = os.path.join(base, f"{today}.json")
    run = build_run(meta, candidate, raw_items)
    run["outcome"] = outcome
    day = append_run(day_path, run, today)
    md_path = os.path.join(base, f"{today}.md")
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
        assert "05:00 UTC / 13:00 台北" in md
        assert "本輪有貢獻：A(1)" in md
        assert "本日一覽" in md and "published 1" in md
    finally:
        shutil.rmtree(d)
    print("newsroom demo OK")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main(sys.argv))
    demo()
