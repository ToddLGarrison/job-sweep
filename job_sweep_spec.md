# Job Sweep Automation — Project Spec

*Version 1.0 | May 2026*

---

## Overview

A Python CLI script that pulls companies from the Notion CRM, checks their ATS job boards for matching open roles, and writes qualifying results directly to the Notion Opportunities database. Updates the Company record after each sweep. Designed to run daily as a manual command or cron job.

---

## Goals

- Automate the mechanical part of the daily sweep: checking known companies for open roles  
- Write qualifying opportunities directly to Notion with correct field mapping  
- Avoid duplicate records via URL-first matching with title fallback  
- Flag Ashby results as unverified since Ashby boards don't return 404 for closed roles  
- Keep the script auditable: print a clear run summary to stdout after every execution

---

## Out of Scope (v1)

- Broadening sweeps beyond existing Notion companies (no external job board search)  
- Fit scoring, priority assignment, or AI-based filtering  
- Cover letter or resume generation  
- Email or Slack notifications  
- Any UI or web interface

---

## Architecture

job-sweep/

├── main.py              \# Entry point and orchestration

├── notion\_client.py     \# All Notion API reads and writes (uses notion-client SDK, not raw requests)

├── scrapers/

│   ├── greenhouse.py    \# Greenhouse board scraper

│   ├── lever.py         \# Lever board scraper

│   └── ashby.py         \# Ashby board scraper (flags results as unverified)

├── matcher.py           \# Role title matching logic

├── deduplicator.py      \# Duplicate detection logic

├── models.py            \# Data models (Company, Opportunity)

├── config.py            \# Constants: target titles, Notion DB IDs, headers

├── requirements.txt

└── README.md

---

## Data Flow

1\. Fetch all Companies from Notion (with ATS, ATS Slug, Company Name, Tier)

2\. For each company with a valid ATS \+ ATS Slug:

   a. Route to the correct scraper (Greenhouse / Lever / Ashby)

   b. Fetch the job listings from that board

   c. Filter listings against the target title list (see Matching Logic)

   d. For each match:

      i.  Run duplicate check against Notion Opportunities

      ii. If not a duplicate, write new Opportunity record to Notion

3\. Update Company record: Last Swept \= today, Hiring \= "Relevant" / "Not" based on results

4\. Print run summary to stdout

---

## Notion Integration

### Companies Database

**ID:** `collection://266cf0ba-f470-8286-9694-07cb7a7d7d72`

Fields read: | Field | Type | Notes | |---|---|---| | Name | title | Company name | | ATS | select | "Greenhouse", "Lever", "Ashby" | | ATS Slug | text | e.g. `klaviyo`, `hex` | | Tier | select | Tier 1 / Tier 2 / Tier 3 |

Fields written: | Field | Type | Notes | |---|---|---| | Last Swept | date | Set to today (YYYY-MM-DD) | | Hiring | select | "Relevant" if any role found, "Not" if none |

**Skip logic:** If ATS or ATS Slug is empty, skip the company and log a warning.

---

### Opportunities Database

**ID:** `collection://eebcf0ba-f470-83bd-8a01-07d8bc25988e`

Fields written on new record creation: | Field | Type | Value | |---|---|---| | Name | title | `{Company} / {Role Title} / {Year}` | | Stage | select | `"Qualification"` | | Source | select | `"Job Sweep"` | | Job URL | url | Direct apply link from ATS board | | Verified | checkbox (string) | `"__NO__"` for Ashby; `"__YES__"` for Greenhouse/Lever | | Company | relation | Link to Company page ID | | Role Type | select | Mapped from title (see Role Type Mapping) | | Notes | text | `"Auto-added by job sweep on {date}. Ashby: manual verification required."` (Ashby only) |

Fields NOT written by the script (left for manual entry):

- Priority, Fit Score, Salary, Application Deadline, Next Step

---

## Scraper Specs

### Greenhouse

- **Board URL pattern:** `https://job-boards.greenhouse.io/{slug}`  
- **Method:** Fetch JSON from `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`  
- **Live status:** Jobs present in the API response are live. Missing \= closed.  
- **Verified:** `__YES__`

### Lever

- **Board URL pattern:** `https://jobs.lever.co/{slug}`  
- **Method:** Fetch JSON from `https://api.lever.co/v0/postings/{slug}?mode=json`  
- **Live status:** Jobs in response are live. No auth required (public API).  
- **Verified:** `__YES__`  
- **Note:** Endpoint confirmed in Lever's official postings-api docs. Returns a JSON array; empty array means no open roles.

### Ashby

- **Board URL pattern:** `https://jobs.ashbyhq.com/{slug}`  
- **Method:** Fetch JSON from `https://api.ashbyhq.com/posting-api/job-board/{slug}`  
- **Live status:** ⚠️ Ashby does NOT return 404 for closed roles. All results flagged as unverified regardless.  
- **Verified:** `__NO__` (always)  
- **Notes field:** Must include: `"Ashby board — manual verification required before applying."`

---

## Target Role Titles

The script matches against these titles (case-insensitive, substring match):

TARGET\_TITLES \= \[

    "Solutions Engineer",

    "Solutions Consultant",

    "Solutions Architect",

    "Customer Success Engineer",

    "Customer Success Manager",

    "Technical Account Manager",

    "Implementation Engineer",

\]

**Matching rule:** A job listing matches if any target title is a case-insensitive substring of the listing's title.

**Examples of what matches:**

- "Senior Solutions Engineer" → matches "Solutions Engineer"  
- "Enterprise Customer Success Manager" → matches "Customer Success Manager"  
- "Associate Implementation Engineer" → matches "Implementation Engineer"

**Examples of what does NOT match:**

- "Sales Engineer" → no match  
- "Support Engineer" → no match  
- "Account Executive" → no match

---

## Role Type Mapping

When writing to Notion, map the matched title to a Role Type select value:

| Matched Title Contains | Role Type |
| :---- | :---- |
| Solutions Engineer | Solutions Engineer |
| Solutions Consultant | Solutions Engineer |
| Solutions Architect | Solutions Engineer |
| Customer Success Engineer | Customer Success |
| Customer Success Manager | Customer Success |
| Technical Account Manager | Customer Success |
| Implementation Engineer | Implementation |

---

## Duplicate Detection

**Step 1 — URL match (primary):** Query Notion Opportunities where `Job URL == {url}`. If any record exists, skip.

**Step 2 — Title fallback:** If Job URL field is empty on existing records, query where `Name contains {Company}` AND `Name contains {Role Title}`. If match found, skip.

**On duplicate found:** Log `SKIP [Company] / [Title] — duplicate found` to stdout. Do not update the existing record.

---

## Company Record Update Logic

After processing all jobs for a company:

- **If 1+ qualifying roles found:** Set `Hiring = "Relevant"`, `Last Swept = today`  
- **If 0 qualifying roles found:** Set `Hiring = "Not"`, `Last Swept = today`  
- **If scraper errored:** Set `Last Swept = today`, do NOT update `Hiring` (leave existing value). Log the error.

---

## Run Summary Output (stdout)

At the end of every run, print:

\=== Job Sweep Complete — {date} \===

Companies swept: {n}

New opportunities added: {n}

Duplicates skipped: {n}

Companies with no matching roles: {n}

Errors: {n}

NEW ROLES ADDED:

  \- {Company} / {Title} / {Year} \[{ATS}\] \[UNVERIFIED\]

  ...

ASHBY — MANUAL VERIFICATION REQUIRED:

  \- {Company} / {Title}: {url}

  ...

ERRORS:

  \- {Company}: {error message}

  ...

---

## Config

All constants live in `config.py`:

NOTION\_API\_KEY \= os.environ\["NOTION\_API\_KEY"\]

COMPANIES\_DB\_ID \= "266cf0ba-f470-8286-9694-07cb7a7d7d72"

OPPORTUNITIES\_DB\_ID \= "eebcf0ba-f470-83bd-8a01-07d8bc25988e"

TARGET\_TITLES \= \[ ... \]  \# see above

ATS\_SCRAPER\_MAP \= {

    "Greenhouse": "scrapers.greenhouse",

    "Lever": "scrapers.lever",

    "Ashby": "scrapers.ashby",

}

`NOTION_API_KEY` must be set as an environment variable. Never hardcode it.

**SDK consistency note:** All Notion reads and writes go through the `notion-client` SDK (`from notion_client import Client`). Do not mix SDK calls with raw `requests` calls to the Notion API. The ATS scrapers (Greenhouse, Lever, Ashby) use raw `requests` since those are third-party APIs with no SDK.

---

## Error Handling

- Network errors (timeouts, 5xx): catch, log to run summary, continue to next company  
- Notion API errors on write: catch, log, do NOT retry automatically  
- Missing ATS/Slug on Company: skip silently, log a warning  
- Ashby JSON parse failures or unexpected response shape: catch, mark company as errored, continue  
- Script should never crash mid-run; all exceptions are caught per-company

---

## Dependencies (requirements.txt)

requests

python-dotenv

notion-client

---

## Running the Script

\# Set env var

export NOTION\_API\_KEY=your\_key\_here

\# Run

cd \~/job-sweep

python main.py

\# Optional: dry run flag (print what would be written, don't write)

python main.py \--dry-run

---

## v2 Backlog (out of scope now, capture for later)

- Broaden sweep to job boards beyond known companies (LinkedIn, Built In Boston, Greenhouse public board search)  
- Fit scoring via Claude API after job description fetch  
- Auto-assign Priority based on fit score \+ tier  
- Slack or email notification on new roles found  
- `--company` flag to sweep a single company on demand  
- Rate limiting and backoff for Notion API calls

