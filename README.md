# SIGNAL

A fintech news desk that curates itself. SIGNAL watches ~20 fintech, banking, and regulatory RSS feeds across Taiwan and global sources, scores what it finds, and rewrites the most important stories into a two-paragraph brief — automatically, every 3 hours, with no per-run API billing.

**Live site:** https://laiyenju.github.io/signal-fintech/

---

## What SIGNAL is

SIGNAL is a static news site with two feeds — **Taiwan (tw)** and **Global** — each showing:

- **本日最重點 / Today's Top Story** — the single most important story of the day, or **本日觀察 / Today's Watch** on quieter days when nothing clears the bar
- **本週要聞 / This Week** — a rolling 7-day list of qualifying stories, newest first, with progressive disclosure past the first 5
- **Sources** and **social discussion** chips per story, plus an "ask AI" shortcut that copies the story context for follow-up questions in ChatGPT / Claude / Gemini

There's no backend, no database, and no paid API calls in the loop — content generation runs entirely inside a Claude Code scheduled cloud routine, using subscription quota rather than metered API usage.

## How it works

```
Claude Code cloud routine (wakes every 3 hours)
    -> scripts/fetch_news.py fetches ~20 RSS feeds (plain fetch, no AI, zero cost)
    -> Claude Code reads the rules below and does the selection + rewrite itself
    -> writes data.json, opens a PR from a claude/* branch, merges it into main
GitHub Pages (free static hosting)
    -> auto-deploys main on every push
Browser
    -> index.html fetches data.json from the same directory and renders it
```

Routine behavior is fully defined in [`排程任務指令.md`](./排程任務指令.md) (the literal prompt pasted into the scheduled task) — editing that file changes selection/rewrite behavior without touching code. Manual setup steps live in [`設定步驟.md`](./設定步驟.md).

## Data sources

Configured in [`scripts/fetch_news.py`](./scripts/fetch_news.py) (`FEEDS` list), currently:

**Taiwan** — 經濟日報, 科技新報, 公視新聞, Yahoo 財經, 中央社 CNA（科技／財經）, 台灣金管會（新聞稿）, MaiCoin Blog

**Global — news & regulators** — TechCrunch Fintech, PYMNTS, Finextra, Banking Dive, The Fintech Times, Bankless, CoinDesk, The Block, Bloomberg Markets, NYT (Dealbook / Economy / Technology), Hacker News, Techmeme, US SEC, EU ESMA, EU EBA, UK FCA, Japan FSA, BIS, Stripe Blog, PayPal Newsroom

**Readwise Reader** — the routine also pulls the last 48h of the owner's Reader feed (RSS + email newsletters) via the Readwise connector: a human-curated layer covering sources plain RSS can't reach (email-only newsletters like 區塊勢, member feeds). Only stories with public URLs get cited; paid-newsletter content is reference-only, never republished.

**Digests** — TLDR Fintech / AI / Dev. These feeds carry titles only, so the fetcher opens each issue page and **explodes it into individual stories** — each with its headline, blurb, and the *original* outlet's link (Reuters, CNBC, Finextra…). They then compete for selection like any other candidate, and are always credited to the original outlet, never to TLDR itself.

**Social** — community discussion is matched per selected story at selection time via the Algolia Hacker News Search API (free, keyless): find the story's HN thread, pull a few substantive top-level comments. No thread, no comments — social sections stay honestly empty rather than fabricated.

Fetching is a plain RSS pull (`feedparser`, 48-hour lookback) — no AI involved and no cost. Sources with no reachable feed are skipped without failing the run.

## Selection & filtering

1. **Score every candidate** on two 0–5 axes: *coverage* (how many tracked sources reported it) and *impact* (regulatory action, real money/market size involved, relevance to Taiwan/global fintech, and evidence — not speculation — of ripple effects). Composite score = impact × 60% + coverage × 40%.
2. **Today's Top Story is decided once per day.** The first run of the day picks the highest-scoring story from the prior 12 hours; if nothing clears an impact threshold, the slot becomes "Today's Watch" instead of forcing a pick. Every later run that day leaves it untouched, no matter what else comes in.
3. **This Week is a 7-day rolling list, not a per-run top-5.** Existing entries older than 7 days are dropped; new candidates scoring ≥2.5 are added; follow-ups on an already-listed story are appended as `context` on the existing entry instead of duplicating it; the list is re-sorted newest-first after every run.
4. **Both scopes get the full treatment.** Taiwan and Global each run the complete selection pipeline independently; the This Week list must never shrink between runs except through 7-day expiry, so one scope can't silently go stale while the other keeps updating.
5. **No fabrication.** Content, sources, and quotes must trace back to the raw RSS data — thin evidence means a shorter brief, never an invented one. Crypto-only stories (CoinDesk/Bankless) are capped so they can't crowd out the rest of a run's picks. Newsletter digests are never presented as a story themselves — only the individual articles they point to.

## Tech stack

- **Frontend:** single static `index.html` (vanilla JS, no build step, no framework)
- **Data:** `scripts/fetch_news.py` (Python + `feedparser`) → `data.json`, fetched client-side
- **Automation:** Claude Code cloud Scheduled Task / Routine — runs the fetch script, applies the rules above, commits, and merges via `gh pr create` + `gh pr merge`
- **Hosting:** GitHub Pages, deployed from `main`

## Repo structure

```
index.html              Site UI — fetches data.json on load, renders both scopes
data.json                Current content; overwritten (per the rules above) by the routine
scripts/fetch_news.py    RSS fetcher — outputs scripts/raw_items.json, zero-cost, no AI
排程任務指令.md            The routine's full instruction set (selection, rewrite, and commit rules)
設定步驟.md                One-time manual setup guide (repo, Pages, routine)
```

## Honesty principles

- **Say less rather than make it up.** Anything that can't be backed by the actual RSS data doesn't get written — including social discussion, sources, and figures.
- **"Today's Watch" is a feature, not a bug.** If nothing in Taiwan cleared the bar that day, the site says so honestly instead of stretching old news to fill the slot.
