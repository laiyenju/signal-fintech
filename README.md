# SIGNAL

A fintech news desk that curates itself. SIGNAL watches RSS feeds across Taiwan and global sources, scores what it finds, and rewrites the most important stories into a two-paragraph brief — automatically every 3 hours, with **no per-run API billing**.

**Live site:** https://laiyenju.github.io/signal-fintech/

> Content generation runs inside a Claude Code cloud routine on subscription quota (not metered API). Fetching is plain RSS — zero AI cost. Hosting is free GitHub Pages.

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
    -> scripts/fetch_news.py pulls RSS feeds (plain fetch, no AI, zero cost)
    -> Claude Code pulls last 48h from Readwise Reader (optional human-curated layer)
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

### Fetch RSS candidates only

```bash
pip install feedparser
python scripts/fetch_news.py
# writes scripts/raw_items.json (48h lookback, no AI)
```

### Prerequisites for the full automated loop

| Piece | Role |
|---|---|
| Python 3 + `feedparser` | RSS fetch |
| Claude Code subscription with cloud Scheduled Tasks / Routines | Selection, rewrite, commit |
| GitHub repo + Pages from `main` | Hosting |
| `gh` CLI in the routine environment | PR create + merge |
| Readwise connector (optional) | Extra newsletter / email-feed candidates |

Full cloud setup: see [`設定步驟.md`](./設定步驟.md).

---

## Data sources

**Source of truth for RSS:** the `FEEDS` list in [`scripts/feeds.py`](./scripts/feeds.py). Names below match the current list; count and membership can change.

**Taiwan** — 經濟日報, 科技新報, 公視新聞, Yahoo 財經, 中央社 CNA (tech + finance)

**Global — news & analysis** — TechCrunch Fintech, PYMNTS, Finextra, Banking Dive, The Fintech Times, Bankless, CoinDesk, The Block, NYT (Dealbook / Economy / Technology), Hacker News, Techmeme

**Digests** — TLDR Fintech / AI / Dev. RSS items are issue titles only, so the fetcher opens each issue page and **explodes it into individual stories** (headline, blurb, original outlet URL). Stories compete like any other candidate and are credited to the **original outlet**, never TLDR.

**Readwise Reader** (routine step, optional) — last 48h of the owner's Reader feed (RSS + email newsletters). Covers sources plain RSS can't reach. Email (`mailto:`) newsletters are now eligible: cite the story's original outlet link when the body contains one, otherwise the newsletter's own public "read online" link (credited to that newsletter). Only real public URLs — paid-newsletter body stays reference-only and is never republished. If the connector fails, the run continues without it.

**Social** — after selection, the routine matches each new story via the Algolia Hacker News Search API (free, keyless). No matching thread → empty social section (never fabricated). **HN only** today; X and Reddit are not wired.

Unreachable feeds are skipped; a single bad source does not fail the run.

### Adding a feed

1. Add an entry to `FEEDS` in `scripts/feeds.py` (`scope`: `"tw"` or `"global"`; set `"digest": True` for TLDR-style digests).
2. **Also** update the `SOURCES` object in `index.html` so the on-site source directory stays in sync.

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
`signal-fintech.wiki.git` repo, one page per day), kept out of the main repo so
daily logs never bloat it. The routine sets `NEWSROOM_DIR` to a wiki clone and
pushes it directly (no PR). The AI's picks stay reviewable:

- **`<date>.json`** — structured: for each run, per-source update counts
  (`windowItems`) and how many of them fed a selected story (`contributed`), plus the
  scored candidate pool with each item's `decision` and a one-line `reason`.
- **`<date>.md`** — a readable editorial diary re-rendered from the JSON each run
  (browsable as a Wiki page). Includes a day summary, Taipei time, candidate funnel
  (`rejectedSummary`), score breakdown (`class` / impact / volume / source),
  silent sources (count + up to 3 names), and which feeds `contributed`.

Logged on **every** run, including no-change and fail-safe runs. `contributed` staying 0
while `windowItems` stays high over time flags a feed worth dropping. To rebuild MD
from an existing day JSON without appending a run:
`python scripts/newsroom.py --render-only path/to/YYYY-MM-DD.json`.

---

## Tech stack

- **Frontend:** single static `index.html` (vanilla JS, no build step)
- **Data:** `scripts/fetch_news.py` → `scripts/raw_items.json` → routine writes root `data.json` (client-fetched; `_generated_at` drives the site footer timestamp)
- **Automation:** Claude Code cloud Scheduled Task / Routine — fetch, select, rewrite, `gh pr create` + `gh pr merge`
- **Hosting:** GitHub Pages from `main`

---

## Repo structure

```
index.html              Site UI — fetches data.json, renders both scopes
data.json               Published content (updated by the routine)
scripts/fetch_news.py   RSS fetcher → scripts/raw_items.json (no AI)
scripts/raw_items.json  Last fetch output (generated)
scripts/feeds.py        Canonical feed roster (imported by fetch_news + newsroom)
scripts/newsroom.py     Renders the per-run selection log (into $NEWSROOM_DIR)
(wiki) <date>.json      Structured selection record, one entry per run (pushed to Wiki)
(wiki) <date>.md        Human-readable editorial diary, re-rendered each run (Wiki page)
排程任務指令.md            Routine prompt (selection, rewrite, commit) — Chinese
設定步驟.md                One-time setup (repo, Pages, routine) — Chinese
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
