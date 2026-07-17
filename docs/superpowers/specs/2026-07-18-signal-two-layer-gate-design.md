# SIGNAL 兩層把關 + 修正迴圈 — 設計

日期：2026-07-18
狀態：設計定案，待實作計畫

## 背景與目標

SIGNAL 目前由一份單體排程指令（`排程任務指令.md`，約 345 行）在 Claude Code cloud
routine 中每 3 小時執行：抓 RSS/Readwise → 選稿 → 改寫 → 組 `data.json` → 推送合併。

兩個痛點：

1. **單體 prompt 太肥易出錯** —— 累積邏輯（cover 鎖定、7 天滾動、80/20 配額、
   crypto 上限、轉存/context 位置）繁雜，LLM 容易在數數字與算日期時看漏。
2. **想要品質把關** —— 針對選稿內容、日期、數量、統整邏輯做控管，不過關就擋下。

**非目標**：不追求平行/加速；不做「自動改規則」式的自我演化（風險過高）。

## 核心決策

| 決策 | 選擇 |
|---|---|
| 把關分層 | 兩層：`validate.py`（硬規則，確定性）+ `signal-reviewer` subagent（編輯判斷）|
| 產出端 | 不拆，保持完整（選稿+累積是緊耦合的一個腦，拆了反而要在 agent 間傳狀態）|
| 失敗處理 | 修正迴圈，最多 N=3 次；仍不過 → fail-safe 保留舊檔並報告 |
| reviewer 工具 | 開 WebFetch（可抽查來源 URL 防虛構）|

**設計原則（ponytail）**：把「該用程式算的」（日期、數量、邏輯）從 LLM 手上拿回來交給
永不漂移的程式；只把「該用判斷的」（選得對不對、寫得好不好）留給 LLM。

## 整體控制流

orchestrator = `排程任務指令.md`，由 cloud routine 主 agent 執行：

```
主 routine
  1. 產出端（現有 7–13 步，維持完整）：fetch → 選稿/累積 → 寫稿
     → 寫出【暫存】candidate.json（不覆蓋 data.json）+ candidate.meta.json
  2. Gate 第一層：python scripts/validate.py candidate.json candidate.meta.json data.json
     → 確定性硬規則，回傳 {ok, violations:[...]}
  3. Gate 第二層：dispatch signal-reviewer subagent
     → 編輯判斷，回傳 {verdict, issues:[{severity, where, problem, fix}]}
  4. 兩層都過 → commit（現有 14 步）
     任一層擋下 → 收集 feedback → 退回產出端修正 → 重跑 gate
     最多 N=3 次；仍不過 → 保留舊 data.json、輸出詳細報告、不 commit
```

## 元件 1：決策側錄檔 `candidate.meta.json`（關鍵介面）

**為什麼需要它**：`data.json` 只存成品（title/paras/sources…），不存「這則是 A/B/C 類、
影響力幾分、報導量幾分」。但 80/20、crypto 上限、cover 影響力門檻、others≥2.5 全靠這些
分類與分數。純看 `data.json`，validate.py 連哪則是 A 哪則是 B 都不知道，無從驗證。

產出端在寫 candidate.json 的同時多吐一份側錄檔，把判斷攤開：

```json
{
  "today": "2026-07-18",
  "tw": {
    "prevCoverEventKey": "台灣Pay整合案",
    "newItems": [
      {"title":"某支付新創完成B輪","role":"cover","class":"A","impact":4,"volume":3,"score":3.6,"isCrypto":false},
      {"title":"某銀行開放API上線","role":"others","class":"A","impact":3,"volume":2,"score":2.6,"isCrypto":false},
      {"title":"某交易所推質押","role":"others","class":"B","impact":3,"volume":2,"score":2.6,"isCrypto":true}
    ]
  },
  "global": { "prevCoverEventKey": "...", "newItems": [ ... ] }
}
```

- `role`：`cover` | `others` | `context`（對應納入 N 的三種新進內容）。
- `newItems` 只列**本次新進內容**（不含轉存、不含 7 天內未動的既有項目）。
- 側錄檔是**暫存檔**（gitignore，不進 repo），只活在一次執行的產出端 → gate 之間。
- reviewer 也讀它，順便查「你標 A 類，我覺得是 C」。

## 元件 2：`scripts/validate.py`（確定性硬規則）

介面：`validate.py <candidate.json> <candidate.meta.json> <現有 data.json>`
→ stdout 印 JSON `{"ok": bool, "violations": [{"rule": "...", "detail": "..."}]}`；
exit code 0=過、非 0=有違規。

檢查項（現有 6.3 驗收條件中「可機器判定」那幾條的程式化版本）：

- **Schema**：JSON 合法；`tw`/`global`/`_generated_at` 存在；cover 套件 + others 欄位齊全；
  每則 cover/others 的 `paras` 恰兩段；陣列欄位缺值用 `[]` 不得 `null`。
- **80/20**：以 meta `newItems` 計 `N`、A/B 數；`B ≤ floor(N×0.2)`、`A ≥ ceil(N×0.8)`；N<5 時 B 上限=0。
- **crypto 上限**：每 scope 新進（role=cover|others）`isCrypto` ≤ 2。
- **cover 門檻**：cover 對應 item 必為 `class=A`；`tier=top` 需 `impact≥3`，否則須為 `watch`；B 類不得為 cover。
- **others 門檻**：新進 others `score ≥ 2.5`。
- **日期**：cover.date 格式；others 全部在今天往前 7 天內；others 依 date 由新到舊排序。
- **cover 鎖定**：若舊 `cover.date == today`，candidate 的 `cover`/`sources`/`coverSocial` 必與舊檔逐欄相同。
- **轉存**：若舊 `cover.date != today` 且舊 cover 有來源且未過期，舊 cover 事件須出現在 candidate 的 others。
- **others 數量不減**：candidate others 數量 ≥ 舊 others 數量 −（因超 7 天而移除者）。
- **去重**：candidate 內無兩則同 eventKey（以 meta/標題為據）。

**自我檢查**：`__main__` 內含 `demo()`，餵一個已知壞的（B 類超標）與一個已知好的 candidate，
`assert` 驗證 violations 正確。無框架、無 fixture。

**與 6.3 的關係**：6.3 之後只保留「判斷題」，機器題以 validate.py 為單一事實來源，避免兩邊漂移。

## 元件 3：`.claude/agents/signal-reviewer.md`（編輯判斷 subagent）

- **frontmatter**：`name: signal-reviewer`、`description`、`tools: Read, Bash, WebFetch`
  —— **不給 Write/Edit/commit**，純審查動不了檔案。
- **輸入**：candidate.json + candidate.meta.json + 舊 data.json + 候選池（raw_items.json）+ 規則。
- **只判斷程式判不了的編輯題**：
  1. **選對事件？** 給了候選池，cover 是不是真的當日最重要的 fintech 事件。
  2. **分類對不對？** 有沒有 C 類混成 A、B 類過度寬鬆。
  3. **摘要準不準？** 用 WebFetch 抽查來源 URL，比對有無虛構數字/引述。
  4. **寫得好不好？** 兩段、無「發生什麼/影響」小標、專有名詞保留原文。
- **輸出**（結構化）：
  ```json
  {"verdict":"pass|fail","issues":[{"severity":"block|minor","where":"tw.cover","problem":"...","fix":"..."}]}
  ```
- `block`（選錯/分類錯/虛構）→ 觸發修正迴圈；`minor`（寫得不夠好）→ 記錄但放行，不無限打磨。

## 元件 4：修正迴圈（在 orchestrator 內）

- 主 routine 持迴圈計數器，上限 N=3。
- 失敗時把 validate.py 的 violations + reviewer 的 block issues 串成具體 feedback，
  退回產出端「修正這些問題後重新產出 candidate.json + meta」。
- **防呆**：同一條 violation 連兩次沒改掉 → 提前中止，不空燒剩餘次數。
- 試滿 3 次仍不過 → 保留舊 `data.json`、不 commit、在任務輸出詳列剩餘違規原因。

## 檔案異動

| 檔案 | 動作 |
|---|---|
| `scripts/validate.py` | 新增（含 `__main__` 自我檢查）|
| `.claude/agents/signal-reviewer.md` | 新增 subagent |
| `排程任務指令.md` | 改：產出端改寫暫存 candidate.json + meta；新增 gate/修正迴圈/fail-safe 段；commit 只在雙層過後；6.3 機器題改指向 validate.py |
| `.gitignore` | 加 `candidate.json`、`candidate.meta.json` |
| `README.md` | 更新流程圖（+gate 層）|

## 在 cloud routine 的可行性

可行。主 agent 用 Bash 跑 `validate.py`、用 Task 派 `signal-reviewer`；前提是
`.claude/agents/signal-reviewer.md` 與 `scripts/validate.py` 都 commit 進 repo。
interactively-authenticated 的 connector（如 Readwise）在 headless 環境可能不可用 ——
沿用現有指令的「connector 不可用則跳過並說明」既有處理。

## 風險與取捨

- **側錄檔與成品不一致**：產出端可能寫錯 meta（例如標 A 實為 C）。緩解：reviewer 的
  「分類對不對」正是查這個；且 meta 錯到違反硬規則時 validate.py 會擋。
- **修正迴圈成本**：每次重做燒 token/時間。緩解：N=3 上限 + 同違規兩次中止。
- **WebFetch 變慢**：reviewer 抽查來源增加延遲。取捨：使用者明確要求，防虛構價值 > 延遲。
