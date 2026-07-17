# SIGNAL 兩層把關 + 修正迴圈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SIGNAL 產出 `data.json` 後、commit 前，加一層確定性程式驗證（`validate.py`）加一層編輯判斷 subagent（`signal-reviewer`），兩層都過才發布，不過則退回產出端修正最多 3 次。

**Architecture:** 產出端維持完整（不拆）。它額外吐一份決策側錄檔 `candidate.meta.json`，讓 `validate.py` 能確定性檢查配額/日期/狀態。`signal-reviewer` subagent 做程式判不了的編輯題（選稿、分類、虛構、文筆、去重、轉存正確性）。orchestrator（`排程任務指令.md`）持修正迴圈。

**Tech Stack:** Python 3（標準庫，`validate.py` 不加任何依賴）、Claude Code subagent（`.claude/agents/*.md`）、既有 cloud routine。

## Global Constraints

- **時區**：「今天」一律以 `TZ=Asia/Taipei` 為準（格式 `YYYY-MM-DD`）。
- **`validate.py` 零依賴**：只用 Python 標準庫（`json`、`sys`、`math`、`datetime`）。
- **側錄檔與候選檔為暫存**：`candidate.json`、`candidate.meta.json` 不進 repo（gitignore）。
- **reviewer 不可寫檔**：`signal-reviewer` 的 `tools` 只含 `Read, Bash, WebFetch`，無 Write/Edit。
- **修正迴圈上限 N=3**；同一條 violation 連兩次沒改掉即提前中止。
- **fail-safe**：任一層最終不過 → 保留舊 `data.json`、不 commit、輸出詳細原因。
- **commit trailer**：每個 commit 訊息結尾空一行後加：
  ```
  Co-authored-by: Grok <grok@x.ai>
  ```
- **檢查分工修訂**：spec 原將「去重」「轉存」列在 `validate.py`；本計畫改列 `signal-reviewer`，因為兩者需要「是否同一事件」的語意判斷，程式難以可靠比對。`validate.py` 只做批次內 `eventKey` 重複這種確定性子集。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `scripts/validate.py` | 確定性驗證：純函式 `validate()` + CLI。無依賴。|
| `scripts/test_validate.py` | `validate.py` 的自我檢查：純 assert，`python scripts/test_validate.py` 直接跑，無 pytest。|
| `.claude/agents/signal-reviewer.md` | 編輯判斷 subagent（prompt 檔）。|
| `排程任務指令.md` | 產出端改吐暫存 candidate + meta；新增 gate/修正迴圈/fail-safe；commit 只在雙層過後。|
| `.gitignore` | 加 `candidate.json`、`candidate.meta.json`。|
| `README.md` | 流程圖加 gate 層。|

**資料契約（所有任務共用）**

`candidate.json`：與現有 `data.json` 相同結構（見 `排程任務指令.md` 第 6.1 節）。

`candidate.meta.json`：
```json
{
  "today": "YYYY-MM-DD",
  "tw": {
    "newItems": [
      {"eventKey": "台灣Pay整合案", "role": "cover", "class": "A",
       "impact": 4, "volume": 3, "score": 3.6, "isCrypto": false}
    ]
  },
  "global": { "newItems": [ ] }
}
```
- `newItems` 只列本次新進內容（`role` ∈ `cover|others|context`）。轉存與 7 天內未動的既有項目不列入。
- `class` ∈ `A|B`；`impact`/`volume` 為 0–5 整數；`score` 為浮點綜合分數；`isCrypto` 為 bool。

`validate.py` 對外介面：
```python
def validate(candidate: dict, meta: dict, prev: dict, today: str) -> list[dict]:
    """回傳 violations 清單，每個 {'rule': str, 'detail': str}；空清單=通過。"""
```
CLI：`python scripts/validate.py <candidate.json> <candidate.meta.json> <data.json>`
→ stdout 印 `{"ok": bool, "violations": [...]}`；exit 0=過、1=有違規。`today` 由 CLI 以 `Asia/Taipei` 計算後傳入 `validate()`。

---

## Task 1: `validate.py` 骨架 + 結構檢查

**Files:**
- Create: `scripts/validate.py`
- Test: `scripts/test_validate.py`

**Interfaces:**
- Produces: `validate(candidate, meta, prev, today) -> list[dict]`；`check_structure(candidate) -> list[dict]`。
- Consumes: 無。

- [ ] **Step 1: 寫失敗測試**（建立 `scripts/test_validate.py`）

```python
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from validate import validate

GOOD = {
    "tw": {"cover": {"date": "2026-07-18", "tier": "top", "title": "t", "paras": ["a", "b"]},
           "sources": [], "coverSocial": [], "context": [], "others": []},
    "global": {"cover": {"date": "2026-07-18", "tier": "watch", "title": "t", "paras": ["a", "b"]},
               "sources": [], "coverSocial": [], "context": [], "others": []},
    "_generated_at": "2026-07-18T00:00:00Z",
}
GOOD_META = {"today": "2026-07-18", "tw": {"newItems": []}, "global": {"newItems": []}}
PREV = {"tw": {"cover": {"date": "2026-07-10", "tier": "top", "title": "old", "paras": ["a", "b"]},
               "sources": [], "coverSocial": [], "context": [], "others": []},
        "global": {"cover": {"date": "2026-07-10", "tier": "top", "title": "old", "paras": ["a", "b"]},
                   "sources": [], "coverSocial": [], "context": [], "others": []},
        "_generated_at": "2026-07-10T00:00:00Z"}

def rules(candidate, meta=GOOD_META, prev=PREV, today="2026-07-18"):
    return {v["rule"] for v in validate(candidate, meta, prev, today)}

def test_good_passes():
    assert validate(GOOD, GOOD_META, PREV, "2026-07-18") == []

def test_missing_toplevel_key():
    bad = {"tw": GOOD["tw"], "global": GOOD["global"]}  # 缺 _generated_at
    assert "structure.toplevel" in rules(bad)

def test_paras_not_two():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["cover"]["paras"] = ["only one"]
    assert "structure.paras" in rules(bad)

def test_bad_tier():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["cover"]["tier"] = "headline"
    assert "structure.tier" in rules(bad)

def test_array_field_null():
    import copy
    bad = copy.deepcopy(GOOD)
    bad["tw"]["sources"] = None
    assert "structure.arrays" in rules(bad)

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print("ALL PASS")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python scripts/test_validate.py`
Expected: FAIL —`ModuleNotFoundError: No module named 'validate'`（檔案還沒建）。

- [ ] **Step 3: 寫最小實作**（建立 `scripts/validate.py`）

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python scripts/test_validate.py`
Expected: PASS — 印出每個 `ok test_...` 與 `ALL PASS`。

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py scripts/test_validate.py
git commit -m "$(printf 'feat: validate.py 結構檢查 + 測試\n\nCo-authored-by: Grok <grok@x.ai>')"
```

---

## Task 2: `validate.py` 配額 / 側錄檔檢查

**Files:**
- Modify: `scripts/validate.py`（新增 `check_quotas`，接進 `validate()`）
- Test: `scripts/test_validate.py`（新增測試）

**Interfaces:**
- Consumes: `check_structure`、`validate` from Task 1；meta `newItems` 契約。
- Produces: `check_quotas(candidate, meta) -> list[dict]`。

- [ ] **Step 1: 寫失敗測試**（append 到 `scripts/test_validate.py`，放在 `if __name__` 之前）

```python
def _meta(scope_items):
    return {"today": "2026-07-18", "tw": {"newItems": scope_items}, "global": {"newItems": []}}

A = {"eventKey": "e1", "role": "others", "class": "A", "impact": 3, "volume": 2, "score": 2.6, "isCrypto": False}

def test_80_20_b_over_cap():
    # N=3, B=1 → floor(3*0.2)=0 → 超標
    items = [dict(A, eventKey="e1"), dict(A, eventKey="e2"),
             dict(A, eventKey="e3", **{"class": "B"})]
    assert "quota.8020" in rules(GOOD, meta=_meta(items))

def test_80_20_ok_large_batch():
    # N=5, B=1 → floor(5*0.2)=1 → 剛好，A>=ceil(5*0.8)=4
    items = [dict(A, eventKey=f"e{i}") for i in range(4)] + [dict(A, eventKey="e5", **{"class": "B"})]
    assert "quota.8020" not in rules(GOOD, meta=_meta(items))

def test_crypto_over_two():
    items = [dict(A, eventKey=f"e{i}", isCrypto=True) for i in range(3)]  # 3 crypto others
    # N=3 全 A，80/20 過；只驗 crypto
    assert "quota.crypto" in rules(GOOD, meta=_meta(items))

def test_others_score_below_threshold():
    items = [dict(A, eventKey="e1", score=2.4)]
    assert "quota.others_score" in rules(GOOD, meta=_meta(items))

def test_b_class_as_cover():
    items = [dict(A, eventKey="e1", role="cover", **{"class": "B"})]
    assert "quota.cover_class" in rules(GOOD, meta=_meta(items))

def test_cover_top_needs_impact_3():
    # candidate.tw.cover.tier=top，但 meta cover impact=2 → 應為 watch
    items = [dict(A, eventKey="e1", role="cover", impact=2)]
    assert "quota.cover_tier" in rules(GOOD, meta=_meta(items))

def test_duplicate_eventkey_in_batch():
    items = [dict(A, eventKey="dup"), dict(A, eventKey="dup")]
    assert "quota.dup_eventkey" in rules(GOOD, meta=_meta(items))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python scripts/test_validate.py`
Expected: FAIL — 例如 `test_80_20_b_over_cap` assert 失敗（`check_quotas` 尚未接上）。

- [ ] **Step 3: 寫最小實作**（在 `validate.py` 加 `check_quotas`，並在 `validate()` 內呼叫）

```python
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
```

在 `validate()` 內加一行：
```python
def validate(candidate, meta, prev, today):
    v = []
    v += check_structure(candidate)
    v += check_quotas(candidate, meta)
    return v
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python scripts/test_validate.py`
Expected: PASS — `ALL PASS`。

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py scripts/test_validate.py
git commit -m "$(printf 'feat: validate.py 配額/側錄檔檢查\n\nCo-authored-by: Grok <grok@x.ai>')"
```

---

## Task 3: `validate.py` 狀態 / 歷史檢查

**Files:**
- Modify: `scripts/validate.py`（新增 `check_state`，接進 `validate()`）
- Test: `scripts/test_validate.py`（新增測試）

**Interfaces:**
- Consumes: `validate` from Tasks 1–2；`prev`（舊 data.json）與 `today`。
- Produces: `check_state(candidate, prev, today) -> list[dict]`。

- [ ] **Step 1: 寫失敗測試**（append 到 `scripts/test_validate.py`，`if __name__` 之前）

```python
import copy as _copy

def _others(dates):
    return [{"date": d, "title": d, "paras": ["a", "b"], "sources": [], "social": [], "context": []} for d in dates]

def test_cover_locked_changed():
    prev = _copy.deepcopy(PREV)
    prev["tw"]["cover"]["date"] = "2026-07-18"  # 今天已鎖
    prev["tw"]["cover"]["title"] = "locked"
    cand = _copy.deepcopy(GOOD)  # cover.title="t" 不同 → 違規
    assert "state.cover_locked" in rules(cand, prev=prev)

def test_others_older_than_7_days():
    cand = _copy.deepcopy(GOOD)
    cand["tw"]["others"] = _others(["2026-07-01"])  # 距 07-18 為 17 天
    assert "state.others_window" in rules(cand)

def test_others_not_sorted():
    cand = _copy.deepcopy(GOOD)
    cand["tw"]["others"] = _others(["2026-07-12", "2026-07-15"])  # 舊在前 → 未由新到舊
    assert "state.others_sorted" in rules(cand)

def test_others_count_decreased():
    prev = _copy.deepcopy(PREV)
    prev["tw"]["others"] = _others(["2026-07-15", "2026-07-14", "2026-07-13"])  # 3 則皆在窗內
    cand = _copy.deepcopy(GOOD)
    cand["tw"]["others"] = _others(["2026-07-15"])  # 剩 1 則、無過期理由 → 違規
    assert "state.others_count" in rules(cand, prev=prev)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python scripts/test_validate.py`
Expected: FAIL — `test_cover_locked_changed` 等 assert 失敗（`check_state` 未接上）。

- [ ] **Step 3: 寫最小實作**（在 `validate.py` 加 `check_state`，並在 `validate()` 呼叫）

```python
def _age(today, d):
    return (_d(today) - _d(d)).days


def check_state(candidate, prev, today):
    v = []
    for scope in ("tw", "global"):
        s = candidate.get(scope, {})
        p = prev.get(scope, {})
        # cover 鎖定：舊 cover.date == today → cover/sources/coverSocial 必逐欄相同
        if p.get("cover", {}).get("date") == today:
            for fld in ("cover", "sources", "coverSocial"):
                if s.get(fld) != p.get(fld):
                    v.append({"rule": "state.cover_locked", "detail": f"{scope} 今日 cover 已鎖定，{fld} 不得變動"})
        others = s.get("others", []) if isinstance(s.get("others"), list) else []
        dates = [o.get("date") for o in others if o.get("date")]
        # 7 天窗口
        for d in dates:
            if _age(today, d) > 7:
                v.append({"rule": "state.others_window", "detail": f"{scope} others 含超過 7 天項目 {d}"})
        # 由新到舊排序
        if dates != sorted(dates, reverse=True):
            v.append({"rule": "state.others_sorted", "detail": f"{scope} others 未依日期由新到舊排序"})
        # 數量不得減少（扣除因超 7 天而移除者）
        prev_others = p.get("others", []) if isinstance(p.get("others"), list) else []
        expired = sum(1 for o in prev_others if o.get("date") and _age(today, o["date"]) > 7)
        expected_min = len(prev_others) - expired
        if len(others) < expected_min:
            v.append({"rule": "state.others_count", "detail": f"{scope} others {len(others)} < 應保留下限 {expected_min}"})
    return v
```

在 `validate()` 加一行：
```python
    v += check_state(candidate, prev, today)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python scripts/test_validate.py`
Expected: PASS — `ALL PASS`。

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py scripts/test_validate.py
git commit -m "$(printf 'feat: validate.py 狀態/歷史檢查\n\nCo-authored-by: Grok <grok@x.ai>')"
```

---

## Task 4: `signal-reviewer` subagent

**Files:**
- Create: `.claude/agents/signal-reviewer.md`

**Interfaces:**
- Consumes: `candidate.json`、`candidate.meta.json`、`data.json`、`scripts/raw_items.json`、`排程任務指令.md`。
- Produces: 標準輸出格式（JSON verdict），供 orchestrator（Task 5）解析。

- [ ] **Step 1: 建立 subagent 檔**

```markdown
---
name: signal-reviewer
description: SIGNAL 產出的編輯視角把關。檢查選稿是否選對事件、分類是否正確、摘要有無虛構、文筆、以及去重與轉存正確性。只審查、不改檔。
tools: Read, Bash, WebFetch
---

你是 SIGNAL 金融科技新聞站的資深主編，用讀者與編輯的眼光審查本次產出。你只審查、不改檔。

## 你會拿到

- `candidate.json`：本次待發布的成品。
- `candidate.meta.json`：產出端的決策側錄（每則新進的 class/impact/volume/score/isCrypto/eventKey）。
- `data.json`：發布前的既有狀態。
- `scripts/raw_items.json`：本次 RSS 候選池。
- `排程任務指令.md`：選稿與改寫規則（第 2–6 節）。

先用 Read 讀入以上檔案。程式（validate.py）已驗過日期/數量/schema 這類硬規則，**你不要重複數數字**，只做程式判不了的編輯題。

## 只判斷這六件事

1. **選對事件**：對照 `raw_items.json` 候選池，每個 scope 的 cover 是不是當日最重要、且真正以 fintech 為核心的事件？有沒有明顯更重要的 A 類被漏選？
2. **分類正確**：抽查 meta 的 class 標記——有沒有 C 類（純幣價、純獲利、例行裁罰、一般財經）被標成 A？B 類是否過度寬鬆（只是「可能影響」就收）？
3. **無虛構**：對每則新進 cover 與 others，用 WebFetch 打開其 `sources[].url`，比對標題兩段摘要裡的關鍵數字、引述、機構名是否真的來自該來源。抓不到或對不上就是 block。
4. **文筆**：paras 恰兩段、沒有「發生什麼／影響／為什麼重要」小標、專有名詞保留原文（必要時括號說明）、繁體中文通順。
5. **去重**：candidate 內有沒有兩則其實是同一事件（標題不同但同一法案／同一機構決議／同一公司同一事件）？既有項目與新進有沒有重複發稿？
6. **轉存正確**：若今日換了 cover，前一個 cover 是否已正確轉存為一則 `others`（date/title/paras/sources/social/context 對應搬移），且舊套件沒有殘留在 scope 層？

## 嚴重度

- `block`：選錯事件、分類錯（C 混成 A）、虛構、去重漏掉、轉存錯誤。這些會觸發修正迴圈。
- `minor`：文筆可再好但不影響正確性。記錄但放行。

## 輸出

只輸出一個 JSON 物件，不要多餘文字：

{"verdict": "pass" | "fail",
 "issues": [
   {"severity": "block" | "minor", "where": "tw.cover", "problem": "具體問題", "fix": "具體怎麼修"}
 ]}

沒有任何 block issue 時 verdict 為 pass（可含 minor）。有任一 block 時 verdict 為 fail。
```

- [ ] **Step 2: 驗證 frontmatter 可被解析**

Run: `python -c "import re,sys; t=open('.claude/agents/signal-reviewer.md',encoding='utf-8').read(); m=re.match(r'^---\n(.*?)\n---', t, re.S); assert m and 'name: signal-reviewer' in m.group(1) and 'tools: Read, Bash, WebFetch' in m.group(1); print('frontmatter ok')"`
Expected: 印出 `frontmatter ok`。

- [ ] **Step 3: 確認工具邊界（無寫檔工具）**

Run: `grep -E '^tools:' .claude/agents/signal-reviewer.md`
Expected: `tools: Read, Bash, WebFetch`（不含 Write/Edit）。

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/signal-reviewer.md
git commit -m "$(printf 'feat: signal-reviewer 編輯把關 subagent\n\nCo-authored-by: Grok <grok@x.ai>')"
```

---

## Task 5: orchestrator 接線（`排程任務指令.md` + gitignore + README）

**Files:**
- Modify: `排程任務指令.md`（第 13、14 節；6.3 加註）
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: `scripts/validate.py`（Task 1–3）、`signal-reviewer`（Task 4）。
- Produces: 完整排程流程，含兩層 gate + 修正迴圈 + fail-safe。

- [ ] **Step 1: gitignore 加暫存檔**

在 `.gitignore` 末尾加兩行：
```
candidate.json
candidate.meta.json
```

- [ ] **Step 2: 改 `排程任務指令.md` 第 13 節（組裝改為產出暫存 + 側錄檔）**

把第 13 節整節換成：

```markdown
## 13. 組裝並產出暫存檔

1. 依第 6 節結構組裝完整結果，寫入 `candidate.json`（**不覆蓋** `data.json`）。
2. 同時寫出 `candidate.meta.json`，記錄本次每則新進內容的判斷：
   - `today`：以 `TZ=Asia/Taipei date +%Y-%m-%d` 取得。
   - 每個 scope 的 `newItems`（只列 role 為 cover/others/context 的新進內容）：
     `{eventKey, role, class, impact, volume, score, isCrypto}`。
   - 轉存與 7 天內未動的既有項目不列入 `newItems`。
3. 先忽略 `_generated_at` 比較 `candidate.json` 與現有 `data.json`。若內容無變化，
   保留原 `data.json` 與原 `_generated_at`，結束本次任務。
4. 若有變化，將 `candidate.json` 的 `_generated_at` 設為目前 UTC ISO 8601 時間。
```

- [ ] **Step 3: 在第 13 與 14 節之間插入新的「13.5 兩層把關與修正迴圈」**

```markdown
## 13.5 兩層把關與修正迴圈

只有第 13 步判定「有變化」時才執行本節。最多重複 3 輪：

1. **第一層（確定性程式）**：
   `python scripts/validate.py candidate.json candidate.meta.json data.json`
   讀取其 JSON 輸出。`ok` 為 false 時，記下所有 `violations`。
2. **第二層（編輯判斷）**：以 Task 工具派 `signal-reviewer` subagent，讓它讀
   `candidate.json`、`candidate.meta.json`、`data.json`、`scripts/raw_items.json` 與本檔規則，
   回傳 `{verdict, issues}`。記下所有 `severity` 為 `block` 的 issue。
3. **判定**：
   - 兩層皆過（validate `ok=true` 且 reviewer 無 block）→ 跳到第 14 節提交。
   - 有任一違規 → 把 validate 的 violations 與 reviewer 的 block issues 串成具體修正清單，
     退回產出端（第 11–13 步）**只修這些問題**後重新產出 `candidate.json` + `candidate.meta.json`，
     回到本節第 1 步，輪數 +1。
4. **防呆**：若本輪的 violations 與上一輪完全相同（同樣的問題沒被修掉），提前中止，不再重試。
5. **fail-safe**：滿 3 輪仍不過，或提前中止 → **保留原 `data.json`、不提交**，在任務輸出詳列
   每一條未解決的 violation 與 block issue 及其位置。reviewer 的 `minor` issue 只記錄、不阻擋。
```

- [ ] **Step 4: 改第 14 節第一句（提交前置條件 + 來源檔）**

把第 14 節開頭：
```markdown
只有第 13 步驗證通過且 `data.json` 確實有變化時才執行本步。
```
改為：
```markdown
只有第 13.5 節兩層把關皆通過、且 `data.json` 確實有變化時才執行本步。
先以驗證通過的 `candidate.json` 覆蓋 `data.json`（`cp candidate.json data.json`），再提交。
```

- [ ] **Step 5: 第 6.3 節加註（機器題以 validate.py 為準）**

在第 6.3 節標題下、第 1 條之前插入一行：
```markdown
> 下列可機器判定的條件（結構、日期窗口與排序、80/20、加密上限、cover 門檻、cover 鎖定、
> others 數量）由 `scripts/validate.py` 確定性驗證；本節保留供人閱讀，機器判定以該程式為單一事實來源。
> 「去重」與「轉存正確性」需同事件語意判斷，由 `signal-reviewer` subagent 負責。
```

- [ ] **Step 6: 更新 README 流程圖**

把 README「How it works」區塊的流程圖：
```
    -> Claude Code applies selection + rewrite rules from 排程任務指令.md
    -> writes data.json, opens a PR from a claude/* branch, merges into main
```
改為：
```
    -> Claude Code applies selection + rewrite rules from 排程任務指令.md
    -> writes candidate.json + candidate.meta.json (staged, not data.json)
    -> gate 1: scripts/validate.py (deterministic: dates, counts, quotas, schema)
    -> gate 2: signal-reviewer subagent (editorial: selection, miscategorization, fabrication)
    -> both pass -> overwrite data.json, open PR from claude/* branch, merge into main
       any fail  -> fix loop (max 3); still failing -> keep old data.json, report
```

- [ ] **Step 7: 驗證文件一致性（無殘留舊敘述）**

Run: `grep -n "candidate.json\|13.5\|validate.py\|signal-reviewer" 排程任務指令.md`
Expected: 第 13、13.5、14、6.3 節都出現對應引用；沒有「直接覆蓋 data.json」的舊敘述殘留在第 13 節。

- [ ] **Step 8: Commit**

```bash
git add 排程任務指令.md .gitignore README.md
git commit -m "$(printf 'feat: 排程流程接入兩層把關與修正迴圈\n\nCo-authored-by: Grok <grok@x.ai>')"
```

---

## Self-Review 結果

- **Spec 覆蓋**：兩層 gate（Task 1–3 validate.py／Task 4 reviewer）、決策側錄檔（Task 1–5 契約與產出）、修正迴圈 N=3 + 防呆 + fail-safe（Task 5 §13.5）、WebFetch 抽查（Task 4 第 3 點）、檔案異動全表（Task 1–5）、cloud routine 可行性（不需程式改動，Task 5 接線即可）。皆有對應任務。
- **分工修訂**：spec 將「去重／轉存」列 validate.py；本計畫改列 reviewer（需事件語意判斷），已在 Global Constraints 與 6.3 加註標明。
- **型別一致**：`validate(candidate, meta, prev, today)`、`check_structure/quotas/state` 命名跨 Task 1–3 一致；meta `newItems` 欄位在契約、測試、`check_quotas` 三處一致；reviewer 輸出 `{verdict, issues:[{severity, where, problem, fix}]}` 與 §13.5 解析一致。
- **無 placeholder**：所有程式步驟含完整可執行程式碼與預期輸出。
```
