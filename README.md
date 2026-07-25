# SIGNAL

A fintech news desk that curates itself. SIGNAL watches RSS feeds across Taiwan and global sources, scores what it finds, and rewrites the most important stories into a two-paragraph brief — automatically every 3 hours, with **no per-run API billing**.

**Live site:** https://laiyenju.github.io/signal-fintech/

> Content generation runs inside a Claude Code cloud routine on subscription quota (not metered API). Fetching is deterministic (RSS + optional Readwise CLI) — zero AI cost. Hosting is free GitHub Pages.

---

## What it is

A static news site with two scopes — **Taiwan (tw)** and **Global** — each showing:

- **本日最重點 / Today's Top Story** — the single most important story of the day, or **本日觀察 / Today's Watch** when nothing clears the bar
- **本週要聞 / This Week** — a rolling 7-day list of qualifying stories, newest first (first 5 shown; the rest expand on demand)
- **Sources** and **social discussion** chips per story, plus **複製詢問 AI** — copies story context and can open ChatGPT / Claude / Gemini for follow-up questions

No backend, no database, no paid API calls in the loop.

---

## How it works

```
Claude Code cloud routine (every 3 hours)
    -> scripts/fetch_news.py pulls designated sources (RSS first; optional Readwise CLI fallback)
    -> Claude Code may also pull last 48h from Readwise Reader feed (exploratory layer)
    -> Claude Code applies selection + rewrite rules from 排程任務指令.md
    -> writes candidate.json + candidate.meta.json (staged, not data.json)
    -> gate 1: scripts/validate.py (deterministic: dates, counts, quotas, schema)
    -> gate 2: signal-reviewer subagent (editorial: selection, miscategorization, fabrication)
    -> both pass -> overwrite data.json, open PR from claude/* branch, merge into main
       any fail  -> fix loop (max 3); still failing -> keep old data.json, report
    -> every run (incl. no-change / fail-safe): scripts/newsroom.py appends
       <date>.json + renders <date>.md (selection audit log) into the GitHub
       Wiki repo (NEWSROOM_DIR), pushed directly — kept out of the main repo
GitHub Pages
    -> deploys main on every push
Browser
    -> index.html fetches data.json from the same directory and renders it
```

Operator docs (Traditional Chinese): full routine prompt in [`排程任務指令.md`](./排程任務指令.md); one-time setup in [`設定步驟.md`](./設定步驟.md). Editing the routine prompt changes selection/rewrite behavior without touching application code.

---

## Quick start

### Preview the site locally

`index.html` loads `data.json` via `fetch`, so open it through a local server (not `file://`):

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

### Fetch designated sources only

```bash
pip install feedparser
python scripts/fetch_news.py
# → scripts/raw_items.json + scripts/feeds_health.json (48h lookback, no AI)
python scripts/audit_feeds.py   # optional: RSS vs Readwise coverage report
```

### Prerequisites for the full automated loop

| Piece | Role |
|---|---|
| Python 3 + `feedparser` | Designated-source fetch |
| Claude Code subscription with cloud Scheduled Tasks / Routines | Selection, rewrite, commit |
| GitHub repo + Pages from `main` | Hosting |
| `gh` CLI in the routine environment | PR create + merge |
| Readwise CLI (`@readwise/cli`, logged in) | Optional: FEEDS fallback + exploratory Reader feed |
| Readwise MCP / connector | Optional alternative to CLI for the exploratory step only |

Full cloud setup: see [`設定步驟.md`](./設定步驟.md).

---

## Data sources

Canonical roster: [`scripts/feeds.py`](./scripts/feeds.py) (`FEEDS`). Fetcher: [`scripts/fetch_news.py`](./scripts/fetch_news.py). One bad source never fails the run.

### Two intake lanes

| Lane | What | Role |
|---|---|---|
| **A. Designated (`FEEDS`)** | Named outlets SIGNAL always tracks | Drives newsroom “silent / active”; credited as the FEED `name` |
| **B. Exploratory (routine)** | Last 48h of the owner’s **Readwise Reader** feed | Newsletters / sources RSS can’t list; optional — skip if unavailable |

Lane A is deterministic Python. Lane B is the routine prompt ([`排程任務指令.md`](./排程任務指令.md) §9): public `http` links only; email digests may be split to original outlet URLs; paid body is never republished.

### How a designated source is fetched (Lane A)

Each `FEEDS` row has `url` (RSS), `scope`, optional `digest`, and:

| Field | Meaning |
|---|---|
| `policy` | `rss_only` (default) · `rss_primary_readwise_fallback` · `readwise_only` |
| `readwise_match` | `{ domains, site_names }` — used only when policy needs Readwise |

**Per run:**

1. Try RSS for every non-`readwise_only` source (HTTP **308** followed; some hosts break on a trailing `/` — prefer the working URL).
2. Keep items in the last **48h** (undated items kept).
3. If `rss_primary_readwise_fallback` and RSS **errors or yields 0 items**, load Reader feed **once** via CLI (`readwise reader-list-documents --location feed`) and keep docs matching `readwise_match`.
4. Emit `raw_items.json` (each item may include `via: "rss" | "readwise"`) and `feeds_health.json`.

**Design choice:** do not switch a source to Readwise only because one run is quiet. Fallback is for **broken / empty transport** when Reader already covers that domain (e.g. CoinDesk after a bad RSS URL). Occasional `windowItems=0` with a healthy feed (Yahoo 財經, TLDR Fintech between issues) is normal — not a failure.

### Silent vs healthy (newsroom)

`windowItems == 0` for a FEED means **no items in this 48h window**, not “this outlet never worked.”

| Status | Meaning |
|---|---|
| `active_rss` | Items from RSS |
| `active_readwise` | Items only via Readwise fallback (still counts as active) |
| `silent` | Zero items this window |

`contributed` still means “selected into the desk,” not “fetched.” High `windowItems` + long-term `contributed=0` → consider dropping the feed.

### Current roster (names may change)

- **Taiwan** — 經濟日報, 科技新報, 公視新聞, Yahoo 財經, 中央社 CNA (tech + finance)
- **Global** — TechCrunch Fintech, PYMNTS, Finextra, Banking Dive, The Fintech Times, Bankless, CoinDesk, The Block, NYT (Dealbook / Economy / Technology), Hacker News, Techmeme
- **Digests** — TLDR Fintech / AI / Dev: issue RSS → open issue page → **explode** into per-story candidates credited to the **original outlet**, never TLDR

**Social** (post-selection): Algolia HN Search only; no thread → empty social (never fabricated).

### Ops: audit, add, change policy

```bash
python scripts/audit_feeds.py
# verdicts: healthy | use_readwise_fallback | subscribe_in_readwise | fix_rss_url | …
```

| Task | Do this |
|---|---|
| Add a source | 1) `FEEDS` in `feeds.py` 2) `SOURCES` in `index.html` |
| RSS broken, Reader has it | Set `policy: "rss_primary_readwise_fallback"` + `readwise_match`; fix `url` if possible |
| RSS weak, not in Reader | Fix URL or subscribe in Reader first — fallback cannot invent coverage |
| Digest-style letter | `"digest": True` (TLDR pattern) |

---

## Editorial rules (summary)

Full rules live in [`排程任務指令.md`](./排程任務指令.md). Day boundaries use **Taiwan time** (`Asia/Taipei`).

1. **Fintech-first eligibility comes before scoring.** New content is classified as direct fintech (A), major finance-adjacent with a concrete fintech consequence (B), or general finance (C, rejected). Technology, a digital product, or new infrastructure must be central for A; earnings, premiums, market moves, mortgages, and routine enforcement do not qualify by scale or coverage alone.
2. **Newly admitted content follows an 80/20 mix per scope and run.** At least 80% must be A; B is optional and capped at `floor(new content × 0.2)`, so batches smaller than 5 admit no B stories. B stories cannot become the cover. A sourced `watch` cover counts as one A story; a status-only watch does not count. The policy applies only to newly written covers, list entries, and context — existing content is never retroactively reclassified or removed.
3. **Score** eligible A/B candidates on two 0–5 axes: *coverage* (how many tracked sources reported it) and *impact* (regulation, real money/market size, Taiwan or global fintech relevance, and *evidence* of ripple effects — not speculation). Composite = impact × 60% + coverage × 40%.
4. **Today's Top Story is locked once per day.** On the first run of a new day, the previous sourced cover bundle rolls into This Week unchanged, then all scope-level cover fields are replaced together. The new cover is the highest-scoring A story from the 24 hours ending at the actual run time, excluding the previous cover's event even when another outlet uses a different headline or URL. Impact must be **≥ 3** for `tier: "top"`; otherwise the slot is **Today's Watch** (`tier: "watch"`). Later runs keep the cover locked but may append a qualifying same-event follow-up to its scope-level `context`. Status-only watches with no sources are not rolled over.
5. **This Week is a 7-day rolling list**, not a per-run top-N. Drop entries older than 7 days; preserve all unexpired entries unchanged; add eligible new candidates with composite **≥ 2.5**; same-event follow-ups append to `context` instead of duplicating; sort newest-first. No hard cap — the UI collapses past the first 5.
6. **Taiwan and Global run independently.** A scope's This Week list must not shrink between runs except by 7-day expiry.
7. **No fabrication.** Thin evidence → shorter brief, never invented facts, sources, or quotes. Pure price/trading crypto stories are rejected; Taiwan and Global each cap other eligible crypto or digital-asset topics at 2 new top-level stories per run. Digest issues are never published as stories — only the articles they point to.

---

## Selection log (newsroom)

Every 3-hour run writes an audit trail to the **GitHub Wiki** (the
`laiyenju/signal-fintech.wiki` repo, one page per day), kept out of the main repo so
daily logs never bloat it. The routine runs `scripts/newsroom_wiki.sh`, which clones
with an authenticated HTTPS remote (env `NEWSROOM_WIKI_TOKEN` or `GH_TOKEN` /
`GITHUB_TOKEN` — a token that can push the **wiki** repo, not a main-only deploy
key), renders via `newsroom.py`, and pushes. Wiki write is **soft-fail**: it must
not block `data.json` publish, but every run must print
`newsroom_wiki=ok|failed|skipped` (also required in the data PR body).

- **`<date>.json`** — per run: source activity (`windowItems`, `viaRss` / `viaReadwise`,
  `status`, `contributed`) and the scored pool (`decision` + one-line `reason`).
- **`<date>.md`** — editorial diary from that JSON (Wiki page): day summary, cover +
  funnel, sources (active / Readwise backfill / silent ≤3 / contributed), decisions.

Logged on **every** run (including no-change / fail-safe). Rebuild MD only:
`python scripts/newsroom.py --render-only path/to/YYYY-MM-DD.json`.
Wiki setup: `設定步驟.md`.

---

## Tech stack

- **Frontend:** single static `index.html` (vanilla JS, no build step)
- **Data:** `fetch_news.py` → `raw_items.json` (+ `feeds_health.json`) → routine writes root `data.json`
- **Automation:** Claude Code cloud routine — fetch, select, rewrite, `gh pr` merge
- **Hosting:** GitHub Pages from `main`

---

## Repo structure

```
index.html                 Site UI — fetches data.json
data.json                  Published content (routine)
scripts/feeds.py           Canonical FEEDS roster + policy / readwise_match
scripts/fetch_news.py      Designated-source fetch → raw_items.json, feeds_health.json
scripts/audit_feeds.py     Offline RSS vs Readwise coverage audit
scripts/newsroom.py        Selection log → $NEWSROOM_DIR
scripts/validate.py        Gate 1 schema / quotas
(wiki) <date>.json|.md     Per-day newsroom audit (not in main repo)
排程任務指令.md               Routine prompt — Chinese
設定步驟.md                   One-time setup — Chinese
```

---

## Honesty principles

- **Say less rather than make it up.** Anything that can't be backed by real source data doesn't get written — including social discussion, sources, and figures.
- **"Today's Watch" is a feature, not a bug.** If a scope cleared no bar that day, the site says so instead of stretching old news to fill the slot.

---

## Related docs

| Doc | Language | Purpose |
|---|---|---|
| [`排程任務指令.md`](./排程任務指令.md) | Chinese | Full prompt pasted into the Claude Code scheduled task |
| [`設定步驟.md`](./設定步驟.md) | Chinese | One-time setup: repo, GitHub Pages, cloud routine |

---

## License

Personal project. No open-source license is declared yet; treat the code and content as all rights reserved unless stated otherwise.
