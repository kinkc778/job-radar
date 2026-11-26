# HK AI / Data Job Scanner

A personal job-hunting agent that runs in the cloud every morning, finds graduate-level
AI, data and solution-engineering roles in Hong Kong, scores every job description against
your CV with DeepSeek, and emails a ranked digest with the title, JD snapshot and apply link.

It is built for one candidate (`cv_profile.json`) and one location (Hong Kong), but every
query, filter and threshold lives in `config.json`.

**Live board:** <https://kinkc778.github.io/job-radar/>

---

## What it does

1. **Collects** live postings from:
   - **LinkedIn guest search** – HK jobs without login; works from cloud IPs
   - **Workable global search** – HK-filtered, full JDs, many startup/grad roles
   - **eFinancialCareers HK** – embedded JSON feed; finance/tech roles
   - **JPMorgan Oracle HCM feed** – HK requisitions with responsibilities/qualifications
   - **ATS boards** – Greenhouse / Lever / Ashby boards of companies with HK offices
     (Binance, OKX, Bybit, Lalamove, Flexport, MongoDB by default)
   - **JobsDB HK** – Playwright + real Chrome; works locally, Cloudflare-blocked in the cloud
   - **CTgoodjobs HK** – JSON-LD via Chrome; works locally, blocked in the cloud
2. **Filters** titles with configurable regexes: keeps data / analytics / AI / ML / LLM /
   agent / solution roles, drops senior, manager, sales and non-technical noise.
3. **Scores** each JD 0-100 against the CV with `DeepSeek-V4.1-Flash-1017`, returning a role family,
   a 2-3 sentence summary, up to 3 "why it fits" bullets and up to 2 gaps.
4. **Emails** an HTML digest (heartbeat at 07:00 HKT, plus any run that finds new roles) with:
   - job title + company + location + salary
   - match score, role family, employment type
   - JD snapshot, why it fits, what's missing
   - a direct apply link
5. **Publishes** a static job board (`docs/`) where you can search, filter, bookmark and
   mark roles as applied. It refreshes with every scan and needs no database.
6. **Remembers** everything it has seen in `data/seen_jobs.json`, so you only get new jobs.
   High scorers that missed the email cap are re-surfaced in later digests.

```
GitHub Actions (every 6 hours)
              │
      python -m jobscan
              │
   ┌──────────┴───────────────────────────┐
   │ Playwright + Chrome    plain HTTP    │
   │   JobsDB HK            CTgoodjobs    │
   │                        ATS JSON APIs │
   └──────────┬───────────────────────────┘
              │
      title prefilter (config.json)
              │
      DeepSeek-V4.1-Flash-1017  ←  cv_profile.json
              │
      HTML email (Gmail SMTP)
              │
      data/seen_jobs.json committed back to the repo
```

---

## 1. Connect the scorer and the mailbox

### Scoring endpoint (private)

The model and its settings live in `config.json`, but the **endpoint URL is private** and
is never committed:

| Setting | Where it lives |
|---|---|
| `LLM_BASE_URL` | `.env` locally, `LLM_BASE_URL` repository secret in Actions |
| `LLM_MODEL`, `reasoning_effort`, `json_mode`, timeout | `config.json` → `scoring` |
| `LLM_API_KEY` | optional; only needed if your endpoint requires a Bearer token |

Locally, add to `.env`:

```
LLM_BASE_URL=https://your-llm-endpoint/v1
```

For the official DeepSeek API, use `https://api.deepseek.com`, model `deepseek-chat`,
and set `LLM_API_KEY` (or `DEEPSEEK_API_KEY`) as a secret.

If the endpoint is unreachable the scanner falls back to a keyword/skill heuristic and
says so in the email footer; the run does not fail.

### Gmail app password (for sending)

Gmail SMTP refuses your normal password. You need a 16-character App Password:

1. Google Account → **Security** → turn on **2-Step Verification** (if not already on).
2. Go to <https://myaccount.google.com/apppasswords>
3. Create an app password named `job-scan`, copy the 16 characters (spaces don't matter).
4. Use that as `SMTP_PASS`, with `SMTP_USER` = your Gmail address.

> If the App Passwords page says it is not available (Workspace account or Advanced
> Protection), switch the mailer to Resend: sign up at resend.com, verify your address,
> and replace the SMTP block in `jobscan/mailer.py` with a Resend API call. The default
> free Resend account can send to your own verified email.

---

## 2. Run it locally first

Requires Python 3.11+ and Google Chrome installed.

```bash
cd "C:/Users/Ken/Desktop/job_scanning"

# one-time
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m playwright install chromium

# credentials (SMTP only; the scoring endpoint needs no key)
cp .env.example .env        # then edit .env and fill in SMTP_USER / SMTP_PASS

# scan, build the report, do NOT email
.venv/Scripts/python -m jobscan --dry-run --limit 20
```

Open the generated `reports/*.html` in a browser. When it looks right, run without
`--dry-run` to receive the email.

Useful flags:

| Flag | Meaning |
|---|---|
| `--dry-run` | scan + report, never email |
| `--sources jobsdb` | only one source (comma-separated: `jobsdb,ctgoodjobs,ats`) |
| `--limit 20` | max JD detail fetches this run (default `max_detail_fetches` in config) |
| `--headed` | show the browser window (useful when debugging Cloudflare) |
| `--verbose` | debug logging |

A full default run takes about **3-5 minutes**.

---

## 3. Deploy free on GitHub Actions

### 3.1 Create a repository

For the free board URL the repository must be **public**: GitHub Pages on private repos
requires a paid plan. Your CV is still not committed — `cv_profile.json` is git-ignored and
is written from the `CV_PROFILE_B64` secret at runtime. The public board is built from job
data only, and `board_include_analysis: false` strips CV-derived notes from it.

On <https://github.com/new>: name it `job-radar`, choose **Public**, create it.

Then, from this folder:

```bash
git init
git add .
git commit -m "HK AI/data job scanner + board"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/job-radar.git
git push -u origin main
```

### 3.2 Add five repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `LLM_BASE_URL` | your private OpenAI-compatible endpoint, e.g. `https://…/v1` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | the 16-character app password |
| `EMAIL_TO` | recipient address for the daily digest |
| `CV_PROFILE_B64` | base64 of your `cv_profile.json` — required in the cloud, never committed |

`CV_PROFILE_B64` is written to `cv_profile.json` at runtime by the workflow, so your CV
never appears in the repository. Generate it with:

```bash
base64 -w0 cv_profile.json          # Linux / Git Bash
```

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("cv_profile.json"))   # PowerShell
```

### 3.3 Turn on the job board

Repo → **Settings → Pages** → Build and deployment → Source: **Deploy from a branch** →
Branch **main**, folder **/docs** → **Save**.

The board appears at `https://<YOUR_USERNAME>.github.io/job-radar/` within a minute.
Every scan commits updated data to `docs/data/jobs.js`, and Pages rebuilds automatically.

The board supports search, role/source/score filters, bookmarks and an applied tracker.
All personal state lives in your browser's `localStorage`; the site itself has no backend.
`board_include_analysis: true` restores the why-it-fits/gaps notes — only do that if the
repo is private.

### 3.4 Test the workflow

Repo → **Actions** → **Daily HK job scan** → **Run workflow**.
Tick `dry_run` for the first run. The HTML report is downloadable from the run's
**Artifacts**; `data/seen_jobs.json` is committed back by the bot.

### 3.4 Schedule

The workflow runs **every 6 hours** — 07:07, 13:07, 19:07 and 01:07 Hong Kong time —
and commits its state back to the repo after each run.

```yaml
on:
  schedule:
    - cron: "7 23,5,11,17 * * *"   # UTC; +8h = 07:07/13:07/19:07/01:07 HKT
```

Only the 07:xx run sends an email when there are no new matches (the daily heartbeat);
the other runs email only when they find something. `send_empty_hour_hkt` in
`config.json` controls which hour sends the heartbeat. The dedupe state means you will
not see the same job twice.

> GitHub disables scheduled workflows after 60 days of repository inactivity.
> This workflow commits after every run, which counts as activity, so it stays enabled.
> If a scheduled run ever misses, use **Run workflow** manually.

---

## 4. Tuning

Everything is in `config.json`:

| Key | What it does |
|---|---|
| `queries` | JobsDB / CTgoodjobs search keywords |
| `min_score` | only email jobs at or above this score (default 55) |
| `include_internships` | `false` excludes internships/placements (default); `--include-interns` overrides for one run |
| `scoring.*` | LLM base URL, model, reasoning effort, timeout, output cap |
| `max_jobs_in_email` | cap per digest (default 20) |
| `max_detail_fetches` | JD pages fetched per run (cost/time control) |
| `backfill_days`, `backfill_max` | re-surface high scorers that missed an earlier email |
| `title_include_regex` | must match to be considered |
| `title_exclude_regex` | senior/lead/manager roles are dropped |
| `blocked_title_regex` | sales, support, HR, property, etc. |
| `sources` | turn any source on/off: `jobsdb`, `ctgoodjobs`, `ats`, `linkedin`, `workable`, `oracle`, `efinancialcareers` |
| `linkedin.pages_per_query`, `efinancialcareers.pages_per_query` | result pages per search query |
| `oracle.host`, `oracle.site`, `oracle.company` | Oracle HCM tenant (JPMorgan by default) |
| `ats.greenhouse`, `ats.lever`, `ats.ashby` | board slugs to scan |
| `board_min_score` | lowest score that appears on the web board (default 50) |
| `board_include_analysis` | include CV-derived why/gaps on the board; keep `false` for a public site |
| `board_keep_days`, `board_max_jobs` | board archive retention |

To add a company, find its board slug:
`boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>` or `jobs.ashbyhq.com/<slug>`,
then add `<slug>` under the matching list. Only HK-located postings are kept.

To change the CV, edit `cv_profile.json`. The scanner reads it at every run — no retraining,
no re-upload.

To re-report a job you already saw, delete its entry from `data/seen_jobs.json`.
To start from scratch, reset that file to:

```json
{ "version": 1, "jobs": {}, "runs": [] }
```

---

## 5. Costs and limits

| Item | Cost |
|---|---|
| GitHub Actions (public repo) | free, unlimited standard-runner minutes |
| GitHub Pages | free for public repos |
| DeepSeek scoring | custom endpoint, no per-call cost |
| Gmail SMTP | free |
| Total | **free** (official DeepSeek API would be ~US$0.01-0.05/day) |

Known limits:

- **Cloud IP blocks.** JobsDB (Cloudflare) and CTgoodjobs (bot wall) reject GitHub's
  datacenter IPs even through Chrome, curl_cffi and cloudscraper — verified by probe.
  The cloud therefore leans on LinkedIn, eFinancialCareers, JPMorgan and the ATS boards;
  JobsDB and CTgoodjobs still contribute when the scanner runs locally. The email's
  *Source health* footer shows which sources succeeded each run.
- **Scores are advice, not a verdict.** The model reads the JD excerpt, not the whole page.
  Always open the apply link before deciding.
- **Personal use only.** Keep request volume low (the scanner pauses between pages);
  job boards' terms restrict bulk scraping.
- Jobs that require 3+ years, senior titles or PhDs are dropped before scoring — that is
  deliberate for a final-year candidate.

---

## 6. Project layout

```
config.json               queries, filters, thresholds, ATS boards
cv_profile.json           structured CV for scoring (git-ignored; supplied via secret)
jobscan/
  main.py                 orchestration + CLI
  config.py               config + .env loading
  browser.py              Playwright Chrome session, Cloudflare detection
  prefilter.py            title relevance + dedupe
  scoring.py              DeepSeek client + heuristic fallback
  state.py                seen_jobs.json (dedupe, backlog, run history)
  report.py               HTML + plain-text digest
  mailer.py               Gmail SMTP
  webexport.py            board archive + docs/data/jobs.js generation
  sources/
    jobsdb.py             Playwright search + JD detail
    ctgoodjobs.py         JSON-LD search + JobPosting detail
    linkedin.py           guest search + JD detail
    workable.py           global HK search + full JD
    efinancial.py         embedded JSON feed
    oracle.py             Oracle HCM feed (JPMorgan)
    ats.py                Greenhouse / Lever / Ashby
docs/                     static job board (index.html, assets, generated data)
data/seen_jobs.json       committed dedupe state
data/board_jobs.json      cumulative board archive
reports/                  local HTML reports (git-ignored, uploaded as CI artifacts)
.github/workflows/scan.yml  6-hourly cron
.env.example              local credentials template
```

### Failure behaviour

- Each source is isolated: one failing board never stops the others.
- If all enabled sources fail, the process exits non-zero and the workflow turns red.
- The email is sent even on a zero-match day (configurable with `send_empty_report`).
