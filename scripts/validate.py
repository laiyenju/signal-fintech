"""SIGNAL 確定性驗證。零依賴，標準庫 only。"""
import json, sys, math
from datetime import date

TIERS = {"top", "watch"}
ARRAY_FIELDS = ("sources", "coverSocial", "context", "others")

# 讀者面文字禁用的內部術語（排程任務指令.md §6.2.1）。
# 只列不會誤傷正常新聞用語的詞；cover/context 等英文欄位名可能撞公司名，交給 reviewer。
BANNED_TERMS = (
    "第2節", "第 2 節",
    "A類", "B類", "C類", "A 類", "B 類", "C 類",
    "寧缺勿濫", "不得虛構", "轉存", "報導佐證",
    "80/20", "Readwise", "raw_items", "TLDR",
)


def _d(s):
    return date.fromisoformat(s)


def _age(today, d):
    return (_d(today) - _d(d)).days


def _safe_age(today, d):
    try:
        return _age(today, d)
    except (ValueError, TypeError):
        return None


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
        sc = meta.get(scope)
        new = sc.get("newItems", []) if isinstance(sc, dict) else []
        if not isinstance(new, list): new = []
        new = [i for i in new if isinstance(i, dict)]
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
        p_cover = p.get("cover")
        if isinstance(p_cover, dict) and p_cover.get("date") == today:
            for fld in ("cover", "sources", "coverSocial"):
                if s.get(fld) != p.get(fld):
                    v.append({"rule": "state.cover_locked", "detail": f"{scope} 今日 cover 已鎖定，{fld} 不得變動"})
        others = s.get("others", []) if isinstance(s.get("others"), list) else []
        # Collect dates with safe age calculation; skip items with unparsable dates
        dates_with_age = []
        for o in others:
            if isinstance(o, dict) and o.get("date"):
                age = _safe_age(today, o["date"])
                if age is not None:
                    dates_with_age.append((o["date"], age))
        dates = [d for d, _ in dates_with_age]
        # 7 天窗口
        for d, age in dates_with_age:
            if age > 7:
                v.append({"rule": "state.others_window", "detail": f"{scope} others 含超過 7 天項目 {d}"})
        # 由新到舊排序
        if dates != sorted(dates, reverse=True):
            v.append({"rule": "state.others_sorted", "detail": f"{scope} others 未依日期由新到舊排序"})
        # 數量不得減少（扣除因超 7 天而移除者）
        prev_others = p.get("others", []) if isinstance(p.get("others"), list) else []
        expired = 0
        for o in prev_others:
            if isinstance(o, dict) and o.get("date"):
                age = _safe_age(today, o.get("date"))
                if age is not None and age > 7:
                    expired += 1
        expected_min = len(prev_others) - expired
        if len(others) < expected_min:
            v.append({"rule": "state.others_count", "detail": f"{scope} others {len(others)} < 應保留下限 {expected_min}"})
    return v


def _as_list(x):
    return x if isinstance(x, list) else []


def _iter_reader_texts(candidate):
    """走訪讀者面文字欄位，產出 (位置, 文字)。sources 一律不檢查（外媒原題）。"""
    for scope in ("tw", "global"):
        s = candidate.get(scope)
        if not isinstance(s, dict):
            continue
        cover = s.get("cover") if isinstance(s.get("cover"), dict) else {}
        yield f"{scope}.cover.title", cover.get("title")
        for i, t in enumerate(_as_list(cover.get("paras"))):
            yield f"{scope}.cover.paras[{i}]", t
        for i, c in enumerate(_as_list(s.get("context"))):
            if isinstance(c, dict):
                yield f"{scope}.context[{i}].title", c.get("title")
                yield f"{scope}.context[{i}].body", c.get("body")
        for i, so in enumerate(_as_list(s.get("coverSocial"))):
            if isinstance(so, dict):
                yield f"{scope}.coverSocial[{i}].body", so.get("body")
        for i, o in enumerate(_as_list(s.get("others"))):
            if not isinstance(o, dict):
                continue
            yield f"{scope}.others[{i}].title", o.get("title")
            for j, t in enumerate(_as_list(o.get("paras"))):
                yield f"{scope}.others[{i}].paras[{j}]", t
            for j, c in enumerate(_as_list(o.get("context"))):
                if isinstance(c, dict):
                    yield f"{scope}.others[{i}].context[{j}].title", c.get("title")
                    yield f"{scope}.others[{i}].context[{j}].body", c.get("body")
            for j, so in enumerate(_as_list(o.get("social"))):
                if isinstance(so, dict):
                    yield f"{scope}.others[{i}].social[{j}].body", so.get("body")


def check_style(candidate):
    v = []
    for path, text in _iter_reader_texts(candidate):
        if not isinstance(text, str):
            continue
        for term in BANNED_TERMS:
            if term in text:
                v.append({"rule": "style.banned_term", "detail": f"{path} 含內部術語「{term}」"})
    # 每則（cover 與各 others 分別計）「報導指出」至多 1 次
    for scope in ("tw", "global"):
        s = candidate.get(scope)
        if not isinstance(s, dict):
            continue
        cover = s.get("cover") if isinstance(s.get("cover"), dict) else {}
        units = [(f"{scope}.cover", cover.get("paras"))]
        for i, o in enumerate(_as_list(s.get("others"))):
            if isinstance(o, dict):
                units.append((f"{scope}.others[{i}]", o.get("paras")))
        for path, paras in units:
            joined = "".join(t for t in _as_list(paras) if isinstance(t, str))
            n = joined.count("報導指出")
            if n > 1:
                v.append({"rule": "style.baodao_repeat", "detail": f"{path} 「報導指出」出現 {n} 次（至多 1 次）"})
    return v


def validate(candidate, meta, prev, today):
    if not isinstance(candidate, dict): candidate = {}
    if not isinstance(meta, dict): meta = {}
    if not isinstance(prev, dict): prev = {}
    v = []
    v += check_structure(candidate)
    v += check_quotas(candidate, meta)
    v += check_state(candidate, prev, today)
    v += check_style(candidate)
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
