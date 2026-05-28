# Job Sweep — Roadmap

## Current State

Job Sweep is a production daily sweep that runs at 6 AM via launchd and delivers an email digest. The following capabilities are live:

**Job boards — main sweep**
Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Comeet, Workable, iCIMS, Rippling, Jobvite, BambooHR — queried via public ATS JSON APIs for each tracked company in Notion.

**Job boards — discovery sweep**
Greenhouse board search API (per title keyword), Lever and Ashby all-jobs (per Notion company), SmartRecruiters and Workday (per Notion company), BuiltInBoston, VentureFizz, YC Work at a Startup. Discovery auto-creates new companies in Notion at Tier 2 when a matching role is found.

**Title matching and classification**
30 target titles across Solutions Engineer, Customer Success, Implementation, and Pre-Sales role families. Senior/Lead/Staff/Principal excluded automatically.

**Red flag detection**
Regex scan of title and JD text for: heavy travel, quota-carrying, outbound sales, tier-1 support only, hardware-only field roles, people management required, wrong industry domain (clinical, pharma, medtech).

**Geographic filtering**
US/remote filter applied to listing location field, title geo-codes (EMEA, APAC, etc.), and description phrase patterns.

**Notion CRM integration**
Companies database (ATS, slug, tier, last swept, hiring status) and Opportunities database (stage pipeline, fit score, expiry tracking, source, verified flag, role type, description).

**Deduplication**
URL-first check against active Notion stages, with name-based fallback.

**Expiry checking**
Open opportunities (Qualification through Contacted/Applied) are re-checked against their ATS URL each sweep. Consecutive misses tracked; auto-closed to Closed Lost at 10 misses. Currently supports Greenhouse, Lever, and Ashby URLs.

**Fit scoring** *(optional)*
Claude Haiku API scores unscored opportunities on a 1–5 star scale by fetching the live JD and evaluating against a defined profile rubric. Triggered with `--score`.

**Daily digest email**
Plain-text email sent at 6 AM covering: new roles from sweep, discovery finds, auto-closed roles, pipeline snapshot (counts per stage), and errors. Stats from the prior evening run are merged in if present.

**launchd scheduling**
One launchd agent: 6:00 AM daily (`com.toddgarrison.jobsweep.morning`), runs `main.py --send-digest`.

**Sweep lockfile**
`/tmp/job_sweep.lock` prevents overlapping runs.

---

## Planned Improvements

1. **ATS data audit and auto-detection script** — Identify companies in Notion with a missing or incorrect ATS value by fetching the company's careers page and fingerprinting the URL patterns against known ATS domains. Produce a human-readable review report. No auto-write to Notion.

2. **Fix error attribution in discovery** — Wrap the `write_opportunity()` call in `discovery.py`'s `_process_listings()` in a `try/except` so that a Notion write failure is attributed to the specific company rather than bubbling up to the enclosing keyword loop.

3. **Deduplicate double `query_by_url` calls in deduplicator.py** — `is_duplicate()` currently calls `query_by_url()` twice (raw URL and normalized URL). Normalize first, skip the second call if the normalized form is identical to the original.

4. **Memory profiling of the discovery sweep** — Investigate high memory usage during large feed processing, particularly the YC Work at a Startup feed. Profile the run and address the root cause.

5. **Scoring and prioritization audit** — Investigate why roles are landing in Qualification but not advancing to Prioritized. Determine whether this is a scoring threshold, workflow, or data issue.

6. **Additional ATS platform support** — Recruitee and Gem are appearing as unknown ATS in error logs. Add scrapers for both.

7. **Wellfound integration** — Currently checked manually. Evaluate feasibility of API or scrape-based automation.
