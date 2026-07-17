"""SIGNAL 確定性驗證。零依賴，標準庫 only。"""
import json, sys, math
from datetime import date

TIERS = {"top", "watch"}
ARRAY_FIELDS = ("sources", "coverSocial", "context", "others")


def _d(s):
    return date.fromisoformat(s)


def _age(today, d):
    return (_d(today) - _d(d)).days


def check_structure(candidate):
    v = []
    for key in ("tw", "global", "_generated_at"):
        if key not in candidate:
            v.append({"rule": "structure.toplevel", "detail": f"缺頂層欄位 {key}"})
    for scope in ("tw", "global"):
        s = candidate.get(scope)
        if not isinstance(s, dict):
            v.append({"rule": "structure.scope", "detail": f"{scope} 不是物件"})
            continue
        cover = s.get("cover", {})
        if not isinstance(cover, dict):
            v.append({"rule": "structure.cover", "detail": f"{scope}.cover 不是物件"})
            cover = {}
        if cover.get("tier") not in TIERS:
            v.append({"rule": "structure.tier", "detail": f"{scope}.cover.tier={cover.get('tier')!r} 非 top/watch"})
        if not (isinstance(cover.get("paras"), list) and len(cover["paras"]) == 2):
            v.append({"rule": "structure.paras", "detail": f"{scope}.cover.paras 必須恰兩段"})
        for fld in ARRAY_FIELDS:
            if not isinstance(s.get(fld), list):
                v.append({"rule": "structure.arrays", "detail": f"{scope}.{fld} 必須是陣列（不得為 null/缺）"})
        for i, o in enumerate(s.get("others", []) if isinstance(s.get("others"), list) else []):
            if not isinstance(o, dict):
                v.append({"rule": "structure.others_item", "detail": f"{scope}.others[{i}] 不是物件"})
                continue
            if not (isinstance(o.get("paras"), list) and len(o["paras"]) == 2):
                v.append({"rule": "structure.paras", "detail": f"{scope}.others[{i}].paras 必須恰兩段"})
    return v


def check_quotas(candidate, meta):
    v = []
    for scope in ("tw", "global"):
        new = meta.get(scope, {}).get("newItems", [])
        n = len(new)
        if n == 0:
            continue
        scope_obj = candidate.get(scope) if isinstance(candidate.get(scope), dict) else {}
        a = sum(1 for i in new if i.get("class") == "A")
        b = sum(1 for i in new if i.get("class") == "B")
        b_cap = 0 if n < 5 else math.floor(n * 0.2)
        if b > b_cap:
            v.append({"rule": "quota.8020", "detail": f"{scope} B 類 {b} > 上限 {b_cap}（N={n}）"})
        if a < math.ceil(n * 0.8):
            v.append({"rule": "quota.8020", "detail": f"{scope} A 類 {a} < 下限 {math.ceil(n * 0.8)}（N={n}）"})
        crypto = sum(1 for i in new if i.get("role") in ("cover", "others") and i.get("isCrypto"))
        if crypto > 2:
            v.append({"rule": "quota.crypto", "detail": f"{scope} 新進加密頂層 {crypto} > 2"})
        for i in new:
            if i.get("role") == "others" and i.get("score", 0) < 2.5:
                v.append({"rule": "quota.others_score", "detail": f"{scope} others {i.get('eventKey')} 分數 {i.get('score')} < 2.5"})
        cover_items = [i for i in new if i.get("role") == "cover"]
        cover_obj = scope_obj.get("cover", {}) if isinstance(scope_obj.get("cover"), dict) else {}
        for ci in cover_items:
            if ci.get("class") != "A":
                v.append({"rule": "quota.cover_class", "detail": f"{scope} cover 必為 A 類，實為 {ci.get('class')}"})
            tier = cover_obj.get("tier")
            if tier == "top" and ci.get("impact", 0) < 3:
                v.append({"rule": "quota.cover_tier", "detail": f"{scope} tier=top 需 impact≥3，實為 {ci.get('impact')}"})
            if tier == "watch" and ci.get("impact", 0) >= 3:
                v.append({"rule": "quota.cover_tier", "detail": f"{scope} impact≥3 應設 top 而非 watch"})
        keys = [i.get("eventKey") for i in new]
        if len(set(keys)) != len(keys):
            v.append({"rule": "quota.dup_eventkey", "detail": f"{scope} newItems eventKey 有重複"})
    return v


def check_state(candidate, prev, today):
    v = []
    for scope in ("tw", "global"):
        s = candidate.get(scope, {})
        p = prev.get(scope, {})
        # Guard against malformed input: ensure dicts
        if not isinstance(s, dict):
            s = {}
        if not isinstance(p, dict):
            p = {}
        # cover 鎖定：舊 cover.date == today → cover/sources/coverSocial 必逐欄相同
        if p.get("cover", {}).get("date") == today:
            for fld in ("cover", "sources", "coverSocial"):
                if s.get(fld) != p.get(fld):
                    v.append({"rule": "state.cover_locked", "detail": f"{scope} 今日 cover 已鎖定，{fld} 不得變動"})
        others = s.get("others", []) if isinstance(s.get("others"), list) else []
        dates = [o.get("date") for o in others if isinstance(o, dict) and o.get("date")]
        # 7 天窗口
        for d in dates:
            if _age(today, d) > 7:
                v.append({"rule": "state.others_window", "detail": f"{scope} others 含超過 7 天項目 {d}"})
        # 由新到舊排序
        if dates != sorted(dates, reverse=True):
            v.append({"rule": "state.others_sorted", "detail": f"{scope} others 未依日期由新到舊排序"})
        # 數量不得減少（扣除因超 7 天而移除者）
        prev_others = p.get("others", []) if isinstance(p.get("others"), list) else []
        expired = sum(1 for o in prev_others if isinstance(o, dict) and o.get("date") and _age(today, o["date"]) > 7)
        expected_min = len(prev_others) - expired
        if len(others) < expected_min:
            v.append({"rule": "state.others_count", "detail": f"{scope} others {len(others)} < 應保留下限 {expected_min}"})
    return v


def validate(candidate, meta, prev, today):
    v = []
    v += check_structure(candidate)
    v += check_quotas(candidate, meta)
    v += check_state(candidate, prev, today)
    return v


def main(argv):
    cand = json.load(open(argv[1], encoding="utf-8"))
    meta = json.load(open(argv[2], encoding="utf-8"))
    prev = json.load(open(argv[3], encoding="utf-8"))
    today = meta.get("today") or date.today().isoformat()
    violations = validate(cand, meta, prev, today)
    print(json.dumps({"ok": not violations, "violations": violations}, ensure_ascii=False, indent=2))
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
