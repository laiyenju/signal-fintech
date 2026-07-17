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
        if cover.get("tier") not in TIERS:
            v.append({"rule": "structure.tier", "detail": f"{scope}.cover.tier={cover.get('tier')!r} 非 top/watch"})
        if not (isinstance(cover.get("paras"), list) and len(cover["paras"]) == 2):
            v.append({"rule": "structure.paras", "detail": f"{scope}.cover.paras 必須恰兩段"})
        for fld in ARRAY_FIELDS:
            if not isinstance(s.get(fld), list):
                v.append({"rule": "structure.arrays", "detail": f"{scope}.{fld} 必須是陣列（不得為 null/缺）"})
        for i, o in enumerate(s.get("others", []) if isinstance(s.get("others"), list) else []):
            if not (isinstance(o.get("paras"), list) and len(o["paras"]) == 2):
                v.append({"rule": "structure.paras", "detail": f"{scope}.others[{i}].paras 必須恰兩段"})
    return v


def validate(candidate, meta, prev, today):
    v = []
    v += check_structure(candidate)
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
