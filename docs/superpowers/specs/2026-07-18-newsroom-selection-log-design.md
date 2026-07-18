# SIGNAL Newsroom 選稿日誌 — 設計規格

**日期**：2026-07-18
**狀態**：待審閱
**目標**：讓每三小時一次的 AI 選稿過程可回溯、可閱讀，並累積成未來汰換資料源的依據。

---

## 1. 問題

SIGNAL 由排程任務（`排程任務指令.md`）每三小時自動選稿。目前：

- 唯一的選稿判斷紀錄 `candidate.meta.json` **在 `.gitignore` 裡**，每輪被覆蓋，沒有歷史。
- 它**只記錄取者**（`newItems` = cover/others/context），不記被淘汰的候選、也不記「為何這則當 cover 不是那則」。
- 沒有任何「本輪哪些資料源有更新」的紀錄，無法判斷哪些 feed 該汰換。

結果：擁有者難以理解、也無法事後稽核 AI 的選稿決策。

## 2. 目標與非目標

**目標**
- 每一輪（含無變化、fail-safe 的輪次）留下一筆**可回溯的結構化紀錄**（稽核用）。
- 在結構化紀錄之上，產生一份**人類可讀的每日編輯室日記**（理解用）。
- 記錄**每個資料源本輪的更新量**，長期累積成汰換依據。
- 紀錄進 git，成為永久歷史。

**非目標（YAGNI）**
- 不記錄「一看就不相關」、資格門檻前就被刷掉的每一則原始項目（只記彙總數）。
- 不做「與上一輪逐則 diff 的真・新增」判斷（見 §7 取捨）。
- 不建前端檢視頁、不做保留期清理（未來需要再說）。

## 3. 範圍決策（已與擁有者確認）

- **兩層**（C）：底層結構化 JSON ＋ 上層可讀 Markdown。
- **計分池深度**（B）：只詳記通過 fintech 資格（A/B 類）、實際被打分的候選；資格前被刷掉的只記彙總數。
- **資料源更新清單**：每輪記錄各資料源在當前 48h 視窗內的項目數（汰換依據）。

## 4. 架構

```
排程任務（雲端，每 3 小時）
  fetch_news.py → scripts/raw_items.json（含每則的 source / scope）
  LLM 選稿 → candidate.json ＋ candidate.meta.json（擴充版，見 §5）
  兩層把關（validate.py ＋ signal-reviewer）
  ── 不論結果如何，本輪結束前呼叫一次 ──
  scripts/newsroom.py <meta> <candidate> <raw_items> <outcome>
      → 讀 raw_items.json 確定性算出各源更新數
      → append 一筆 run 進 newsroom/<today>.json
      → 由該 json 完整重繪 newsroom/<today>.md
  git add newsroom/<today>.json newsroom/<today>.md（＋ data.json 若有變化）
```

**關鍵原則：newsroom 紀錄與 data.json 是否變動解耦。** 每一輪都寫一筆 newsroom 紀錄並提交——包含「無變化」和「fail-safe 未提交」的輪次，因為那些正是最想事後查的情況。

**職責切分**
- **LLM**：只產出它擅長的結構化 JSON（計分、決策、理由）。
- **newsroom.py**：確定性地算資料源統計、append、渲染 Markdown。把「格式一致性」這種 LLM 最易搞砸的事交給程式。

## 5. `candidate.meta.json` 擴充（加欄位，不動既有契約）

> **硬約束**：`validate.py` 讀取 `meta.today` 與 `meta[scope].newItems`（欄位 `eventKey/role/class/impact/score/isCrypto`）。這兩者**維持原樣**，新欄位一律是新增的兄弟欄位，validate.py 會忽略它們。

```jsonc
{
  "today": "2026-07-18",                    // 既有，不動
  "runAt": "2026-07-18T05:00:00Z",          // 新增：本輪 UTC ISO 時戳，作為 run 的唯一 id
  "outcome": "published",                    // 新增：published | no_change | fail_safe
  "notes": "本輪整體編輯判斷，一到三句（可空字串）",  // 新增：run 級編輯註記

  "tw": {
    "newItems": [ /* 既有，validate.py 契約，不動 */
      {"eventKey":"…","role":"cover","class":"A","impact":4,"volume":3,"score":3.6,"isCrypto":false}
    ],
    "scoredPool": [                          // 新增：B 深度。所有「過資格＋被打分」的候選（含落選）
      {
        "eventKey": "…",
        "source": "TechCrunch Fintech",     // 該候選來自哪個資料源（來自 raw_items）
        "class": "A",
        "impact": 4, "volume": 3, "score": 3.6,
        "decision": "cover",                 // cover | others | context | dropped
        "reason": "一句中文：為何這樣判，尤其落選或未當 cover 的原因"
      }
    ],
    "rejectedSummary": {"total": 42, "eligible": 8, "ineligible": 34}  // 新增：資格門檻前後的計數
  },
  "global": { /* 同 tw 結構 */ }
}
```

- `scoredPool` 是 `newItems` 事件的超集（前者含 `dropped`，後者只含進站者）。兩者並存的重複是刻意的——`newItems` 是不可動的把關契約，`scoredPool` 是較豐富的稽核視角。
- `reason` 是本設計的核心新增：現在唯一被明文寫下的「編輯決策理由」。

## 6. Newsroom 檔案格式

### 6.1 `newsroom/<today>.json`（結構化，機器可讀）

```jsonc
{
  "date": "2026-07-18",
  "runs": [
    {
      "runAt": "2026-07-18T05:00:00Z",
      "outcome": "published",
      "notes": "…",
      "sources": [                           // newsroom.py 由 raw_items.json 確定性算出
        {"name":"TechCrunch Fintech","scope":"global","windowItems":6,"contributed":2},
        {"name":"公視新聞","scope":"tw","windowItems":0,"contributed":0}
      ],
      "tw":     {"cover":{"tier":"top","headline":"…","eventKey":"…"},
                 "scoredPool":[…], "rejectedSummary":{…}},
      "global": {…}
    }
    // 同一天最多 8 筆 run，依 runAt append
  ]
}
```

- `sources[].windowItems`：該源在 `raw_items.json` 當前視窗的項目數（0 = 本輪靜默）。
- `sources[].contributed`：該源有幾則進入 `scoredPool` 且 `decision != dropped`（汰換分析的關鍵訊號：長期 windowItems 高但 contributed 恆為 0 → 該汰換）。

### 6.2 `newsroom/<today>.md`（人類可讀日記）

由 `<today>.json` **完整重繪**（非手動 append，確保冪等）。每筆 run 一個區塊：

```markdown
# 2026-07-18 選稿日誌

## 13:00（published）
**TW 頭條**：〈…〉(top, impact 4)
**Global 頭條**：〈…〉(top, impact 5)

**資料源動態**：本輪 18 源、其中 3 源靜默（公視新聞、Yahoo 財經、NYT Economy）。
最活躍：TechCrunch Fintech(6)、Finextra(5)。

**編輯決策（TW）**
- ✅ cover　〈A 事件〉 score 3.6 — 影響力最高的 A 類，鎖為今日頭條
- ▫️ others 〈B 事件〉 score 2.8 — 進本週要聞
- ✗ dropped 〈C 事件〉 score 2.1 — 分數未達 2.5，落選

_編輯註記：…_

---
（下一輪…）
```

## 7. 資料源「更新」的定義與取捨

`raw_items.json` 是 48h 滾動視窗，同一則項目會連續出現在約 16 輪中。因此 `windowItems` 是「該源在視窗內的項目數」，**不是「相對上一輪的真・新增」**。

**取捨（ponytail）**：不做逐輪 diff。理由——汰換依據要的是趨勢，而「某源長期 windowItems 恆為 0、或恆高卻 contributed=0」用視窗數＋contributed 就能判斷，不必committing 龐大的逐輪 link 集合。真・逐輪新增列為未來可選增強，非本次範圍。

## 8. 排程指令（`排程任務指令.md`）改動

1. **第 13 步**：擴充 `candidate.meta.json` 內容（§5 的新欄位）。既有 `newItems`／`today` 不動。
2. **新增一節「寫入 newsroom 日誌」**，由以下三個分支各呼叫一次，帶對應 `outcome`：
   - 13.3 無變化分支 → `outcome=no_change`，跑 newsroom.py，commit newsroom 檔，結束。
   - 13.5.5 fail-safe 分支 → `outcome=fail_safe`，跑 newsroom.py，commit newsroom 檔。
   - 第 14 步 已提交分支 → `outcome=published`，跑 newsroom.py，newsroom 檔＋data.json 一起 commit。
3. 每輪**恰呼叫一次** newsroom.py（在把關迴圈收斂之後，非每次重試都寫），避免同輪重複紀錄。

## 9. `scripts/newsroom.py`

- **輸入**：`candidate.meta.json`、`candidate.json`、`scripts/raw_items.json`、`outcome`。
- **行為**：
  1. 由 raw_items.json 依 `source`+`scope` 分組算 `windowItems`；由 meta.scoredPool 算各源 `contributed`。
  2. 由 candidate.json 取各 scope 的 cover tier/headline（供 md 摘要）。
  3. Append 一筆 run 進 `newsroom/<today>.json`（不存在則建立）；以 `runAt` 為 key，若已存在則取代（冪等）。
  4. 由 json 完整重繪 `newsroom/<today>.md`。
  5. 印一行確認訊息。
- **零依賴**（標準庫 only，與 validate.py 一致）。
- **自我檢查**：`__main__` 內一個 `demo()`，用合成的 meta＋raw 斷言「run 有被 append」「md 含 cover headline」「靜默源 windowItems=0」。無框架。

## 10. 對既有系統的影響

- `validate.py`：**零改動**（新欄位被忽略）。
- `fetch_news.py`：零改動。
- `.gitignore`：`newsroom/` 未被忽略，維持原樣即可（確認 candidate 檔仍被忽略）。
- 前端 `index.html`：零改動。

## 11. 檔案增減清單

| 動作 | 檔案 |
|---|---|
| 新增 | `scripts/newsroom.py` |
| 新增（執行期產生） | `newsroom/<YYYY-MM-DD>.json`、`newsroom/<YYYY-MM-DD>.md` |
| 修改 | `排程任務指令.md`（第 13 步擴充 meta；新增 newsroom 節；三分支各呼叫一次） |
| 修改 | `README.md`（架構圖與檔案樹加入 newsroom） |

## 12. 驗收標準

1. 跑一輪後，`newsroom/<today>.json` 有一筆 run，含 sources、scoredPool（含 reason）、rejectedSummary。
2. `newsroom/<today>.md` 可讀，正確顯示頭條、靜默源、每則決策與理由。
3. 無變化與 fail-safe 的輪次也各留一筆紀錄。
4. `newsroom.py` 的 `demo()` 自我檢查通過。
5. `validate.py` 既有測試（`test_validate.py`）全數通過，未受 meta 擴充影響。
