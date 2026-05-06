# Job Sweep

Pulls companies from the Notion CRM, checks their ATS job boards for matching open roles, and writes qualifying results to the Notion Opportunities database.

## Setup

```bash
pip install -r requirements.txt
```

Set your Notion API key as an environment variable or in a `.env` file:

```bash
export NOTION_API_KEY=your_key_here
# or add NOTION_API_KEY=your_key_here to .env
```

## Usage

```bash
python main.py
```

Dry run — prints what would be written without making any Notion changes:

```bash
python main.py --dry-run
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | Orchestration, run summary output |
| `notion_api.py` | All Notion reads/writes via notion-client SDK |
| `scrapers/greenhouse.py` | Greenhouse ATS scraper |
| `scrapers/lever.py` | Lever ATS scraper |
| `scrapers/ashby.py` | Ashby ATS scraper (results always flagged unverified) |
| `matcher.py` | Role title matching and role type mapping |
| `deduplicator.py` | URL-first duplicate detection with name fallback |
| `models.py` | Company, JobListing, Opportunity dataclasses |
| `config.py` | Constants: DB IDs, target titles, ATS map |
