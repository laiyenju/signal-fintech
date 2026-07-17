"""SIGNAL 確定性驗證。零依賴，標準庫 only。"""
import json, sys, math
from datetime import date

TIERS = {"top", "watch"}
ARRAY_FIELDS = ("sources", "coverSocial", "context", "others")


def _d(s):
    return date.fromisoformat(s)


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
        for ci in cover_items:
            if ci.get("class") != "A":
                v.append({"rule": "quota.cover_class", "detail": f"{scope} cover 必為 A 類，實為 {ci.get('class')}"})
            tier = candidate.get(scope, {}).get("cover", {}).get("tier")
            if tier == "top" and ci.get("impact", 0) < 3:
                v.append({"rule": "quota.cover_tier", "detail": f"{scope} tier=top 需 impact≥3，實為 {ci.get('impact')}"})
            if tier == "watch" and ci.get("impact", 0) >= 3:
                v.append({"rule": "quota.cover_tier", "detail": f"{scope} impact≥3 應設 top 而非 watch"})
        keys = [i.get("eventKey") for i in new]
        if len(set(keys)) != len(keys):
            v.append({"rule": "quota.dup_eventkey", "detail": f"{scope} newItems eventKey 有重複"})
    return v


def validate(candidate, meta, prev, today):
    v = []
    v += check_structure(candidate)
    v += check_quotas(candidate, meta)
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
