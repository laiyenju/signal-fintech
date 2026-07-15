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
    -> writes data.json, opens a PR from a claude/* branch, merges into main
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

**Source of truth for RSS:** the `FEEDS` list in [`scripts/fetch_news.py`](./scripts/fetch_news.py). Names below match the current list; count and membership can change.

**Taiwan** — 經濟日報, 科技新報, 公視新聞, Yahoo 財經, 中央社 CNA (tech + finance)

**Global — news & analysis** — TechCrunch Fintech, PYMNTS, Finextra, Banking Dive, The Fintech Times, Bankless, CoinDesk, The Block, NYT (Dealbook / Economy / Technology), Hacker News, Techmeme

**Digests** — TLDR Fintech / AI / Dev. RSS items are issue titles only, so the fetcher opens each issue page and **explodes it into individual stories** (headline, blurb, original outlet URL). Stories compete like any other candidate and are credited to the **original outlet**, never TLDR.

**Readwise Reader** (routine step, optional) — last 48h of the owner's Reader feed (RSS + email newsletters). Covers sources plain RSS can't reach. Only public URLs may be cited; paid-newsletter body is reference-only and never republished. If the connector fails, the run continues without it.

**Social** — after selection, the routine matches each new story via the Algolia Hacker News Search API (free, keyless). No matching thread → empty social section (never fabricated). **HN only** today; X and Reddit are not wired.

Unreachable feeds are skipped; a single bad source does not fail the run.

### Adding a feed

1. Add an entry to `FEEDS` in `scripts/fetch_news.py` (`scope`: `"tw"` or `"global"`; set `"digest": True` for TLDR-style digests).
2. **Also** update the `SOURCES` object in `index.html` so the on-site source directory stays in sync.

---

## Editorial rules (summary)

Full rules live in [`排程任務指令.md`](./排程任務指令.md). Day boundaries use **Taiwan time** (`Asia/Taipei`).

1. **Score** each candidate on two 0–5 axes: *coverage* (how many tracked sources reported it) and *impact* (regulation, real money/market size, Taiwan or global fintech relevance, and *evidence* of ripple effects — not speculation). Composite = impact × 60% + coverage × 40%.
2. **Today's Top Story is locked once per day.** First run of the day (when `cover.date` ≠ today) picks the highest-scoring story in a ~12h window ending at 06:00 Taiwan time (falls back to 24–48h if needed). Impact must be **≥ 3** for `tier: "top"`; otherwise the slot is **Today's Watch** (`tier: "watch"`). Later runs that day never replace the cover.
3. **This Week is a 7-day rolling list**, not a per-run top-N. Drop entries older than 7 days; add new candidates with composite **≥ 2.5**; same-event follow-ups append to `context` instead of duplicating; sort newest-first. No hard cap — the UI collapses past the first 5.
4. **Taiwan and Global run independently.** A scope's This Week list must not shrink between runs except by 7-day expiry.
5. **No fabrication.** Thin evidence → shorter brief, never invented facts, sources, or quotes. Pure crypto noise is capped (**at most 2 new pure-crypto items per run** for global). Digest issues are never published as stories — only the articles they point to.

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
