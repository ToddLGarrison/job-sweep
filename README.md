# Job Sweep

Job Sweep is a Python automation that runs daily against a curated list of companies stored in a Notion CRM. It queries each company's ATS via public JSON APIs, filters job listings by target title and US geography, runs red-flag detection on the description, deduplicates against existing Notion records, and writes matching opportunities to a Notion Opportunities database. After the main sweep, a discovery pass searches broader job aggregators for roles at companies not yet in the Notion list. Results are summarized in a daily email digest sent at 6 AM.

---

## How It Works

**1. Company sweep**
`main.py` reads all companies from the Notion Companies database. For each company it:
- Calls the appropriate ATS scraper to fetch live job listings
- Filters non-US listings by location field and title geo-codes
- Matches listing titles against `TARGET_TITLES`, excluding seniority keywords (`Senior`, `Lead`, etc.)
- Checks each match against the Notion Opportunities database for duplicates (URL-first, name fallback)
- Scans the job description for red flags (quota, heavy travel, people management, wrong domain, etc.)
- Writes new opportunities to Notion with stage `Qualification`
- Updates the company's `Last Swept` date and `Hiring` status

**2. Discovery sweep**
After the main sweep, `discovery.py` searches for roles at companies not yet in the tracked list by querying:
- Greenhouse board search API (per title keyword)
- Lever and Ashby boards for all companies already in Notion
- SmartRecruiters and Workday boards for all companies already in Notion
- BuiltInBoston (scraped with TLS impersonation via curl_cffi)
- VentureFizz (scraped)
- YC Work at a Startup (parsed from the sales/GTM listing page)

Listings are classified by title match or secondary JD keyword scan (2+ matching keywords). New companies are auto-created in Notion at Tier 2. Ashby results are flagged unverified.

**3. Expiry check**
`expiry_checker.py` re-checks every open opportunity (stages: Qualification, Prioritized, Create Resume, Contacted/Applied) against its original ATS URL. Consecutive misses are tracked; at 10 missed sweeps the opportunity is auto-closed to `Closed Lost`. Supported for Greenhouse, Lever, and Ashby URLs (inferred from the URL domain).

**4. Fit scoring** *(optional, `--score` flag)*
`scorer.py` fetches the job description page for each unscored opportunity and calls the Claude Haiku API to produce a 1–5 star fit rating, which is written back to Notion.

**5. Digest email**
`digest.py` builds a plain-text email summarizing new roles, discovery finds, auto-closed roles, a pipeline snapshot (counts per stage), and any errors. The digest merges stats from both the 6 AM sweep and any prior run persisted to `/tmp/job_sweep_last_run.json`. Delivered via SMTP with STARTTLS.

---

## ATS Boards Supported

**Main sweep (direct company boards)**

| ATS | Module |
|-----|--------|
| Greenhouse | `scrapers/greenhouse.py` |
| Lever | `scrapers/lever.py` |
| Ashby | `scrapers/ashby.py` |
| SmartRecruiters | `scrapers/smartrecruiters.py` |
| Workday | `scrapers/workday.py` |
| Comeet | `scrapers/comeet.py` |
| Workable | `scrapers/workable.py` |
| iCIMS | `scrapers/icims.py` |
| Rippling | `scrapers/rippling.py` |
| Jobvite | `scrapers/jobvite.py` |
| BambooHR | `scrapers/bamboohr.py` |

**Discovery sources**

| Source | Module |
|--------|--------|
| Greenhouse board search API | `scrapers/discovery_greenhouse.py` |
| Lever (all-jobs per company) | `scrapers/discovery_lever.py` |
| Ashby (all-jobs per company) | `scrapers/discovery_ashby.py` |
| BuiltInBoston | `scrapers/discovery_builtinboston.py` |
| VentureFizz | `scrapers/discovery_venturefizz.py` |
| YC Work at a Startup | `scrapers/discovery_yc.py` |

Expiry checking infers ATS from URL domain and currently supports Greenhouse, Lever, and Ashby URLs.

---

## Setup

**Install dependencies**

```bash
pip install -r requirements.txt
```

Key packages: `requests`, `notion-client`, `python-dotenv`, `anthropic`, `beautifulsoup4`, `curl_cffi`.

**Environment variables**

Create a `.env` file in the project root (or export these variables):

```env
NOTION_API_KEY=secret_...        # Required — Notion integration token

# Digest email (all required if --send-digest is used)
DIGEST_EMAIL_TO=you@example.com
DIGEST_EMAIL_FROM=sender@example.com
DIGEST_SMTP_HOST=smtp.example.com
DIGEST_SMTP_PORT=587             # Default: 587
DIGEST_SMTP_USER=smtp_user
DIGEST_SMTP_PASSWORD=smtp_pass

# Optional — required only for --score
ANTHROPIC_API_KEY=sk-ant-...
```

**Notion database IDs**

Two Notion database IDs are hardcoded in `config.py`:

| Constant | Purpose |
|----------|---------|
| `COMPANIES_DB_ID` | List of companies with ATS, slug, tier, and hiring status |
| `OPPORTUNITIES_DB_ID` | Job opportunities with stage, fit score, and expiry tracking |

**launchd scheduling (macOS)**

A single launchd agent fires at 6:00 AM daily:

```
~/Library/LaunchAgents/com.toddgarrison.jobsweep.morning.plist
```

It runs `main.py --send-digest` and writes logs to `logs/morning.log` and `logs/morning.err.log`.

---

## Running Manually

```bash
# Full sweep (no digest email)
python main.py

# Dry run — prints what would be written, no Notion changes
python main.py --dry-run

# Full sweep + digest email
python main.py --send-digest

# Skip the expiry check
python main.py --skip-expiry

# Score unscored opportunities via Claude API after sweep
python main.py --score
```

Flags can be combined: `python main.py --dry-run --skip-expiry`.

A lockfile at `/tmp/job_sweep.lock` prevents concurrent runs.

---

## Project Structure

| Path | Purpose |
|------|---------|
| `main.py` | Entry point — orchestrates sweep, discovery, expiry, scoring, digest |
| `config.py` | Constants: DB IDs, target titles, ATS scraper map, discovery/digest config |
| `notion_api.py` | All Notion reads and writes via notion-client SDK, with retry/backoff |
| `models.py` | `Company`, `JobListing`, `DiscoveryListing`, `Opportunity` dataclasses |
| `matcher.py` | Title matching and role-type classification |
| `deduplicator.py` | URL-first duplicate detection with name fallback |
| `red_flag_detector.py` | Regex-based JD scanning: travel, quota, outbound, management, domain |
| `geo_filter.py` | US/remote location filter for listing fields and title geo-codes |
| `discovery.py` | Discovery sweep across aggregators and ATS board APIs |
| `expiry_checker.py` | Re-checks open opportunity URLs; auto-closes after 10 consecutive misses |
| `scorer.py` | Claude Haiku fit scoring for unscored opportunities |
| `digest.py` | Builds and sends the daily plain-text email digest |
| `scrapers/greenhouse.py` | Greenhouse JSON API scraper |
| `scrapers/lever.py` | Lever JSON API scraper |
| `scrapers/ashby.py` | Ashby JSON API scraper |
| `scrapers/smartrecruiters.py` | SmartRecruiters API scraper |
| `scrapers/workday.py` | Workday API scraper |
| `scrapers/comeet.py` | Comeet API scraper |
| `scrapers/workable.py` | Workable API scraper |
| `scrapers/icims.py` | iCIMS API scraper |
| `scrapers/rippling.py` | Rippling API scraper |
| `scrapers/jobvite.py` | Jobvite API scraper |
| `scrapers/bamboohr.py` | BambooHR API scraper |
| `scrapers/discovery_greenhouse.py` | Greenhouse board keyword search for discovery |
| `scrapers/discovery_lever.py` | Lever all-jobs fetch for discovery |
| `scrapers/discovery_ashby.py` | Ashby all-jobs fetch for discovery |
| `scrapers/discovery_builtinboston.py` | BuiltInBoston scraper (curl_cffi) |
| `scrapers/discovery_venturefizz.py` | VentureFizz scraper |
| `scrapers/discovery_yc.py` | YC Work at a Startup scraper |
| `scrapers/ats_detector.py` | ATS detection from job apply URLs, with redirect resolution |
