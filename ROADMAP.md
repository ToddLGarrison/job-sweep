# Job Sweep — Build Roadmap

## Completed
- [x] Core sweep script (Greenhouse, Lever, Ashby)
- [x] Notion integration — company list, opportunity creation, deduplication
- [x] Role classification and title matching
- [x] Dry run mode
- [x] launchd scheduling — 6am and 10pm daily
- [x] ATS slug backfill for all supported companies

## In Progress / Up Next

- [ ] 1. Slug audit — verify all Greenhouse/Lever/Ashby companies have ATS + slug populated
- [ ] 2. Discovery mode — search ATS boards by title keywords to find new companies and roles outside the existing Notion list
- [ ] 3. Expand ATS support — Workday and SmartRecruiters
- [ ] 4. Built In Boston / VentureFizz scraping — structured scrape for Boston-area and hybrid roles
- [ ] 5. Red flag detection — keyword scan JD text before writing to Notion; skip roles matching auto-exclude criteria (travel, people management, Java/Docker must-have, comp below $80K)
- [ ] 6. Role expiry detection — re-check existing open opportunities against ATS; mark Closed Lost only if listing has been gone for 2-3 consecutive sweeps AND stage is Qualification or Prioritized
- [ ] 7. Batch fit scoring via Claude API — one call per day scoring all new roles against resume; write fit score back to Notion
- [ ] 8. Daily digest — Notion page or log summarizing new roles found, roles flagged, expiring opportunities, and top actions
- [ ] 9. Weekly pipeline report — auto-generated Sunday night summary of full pipeline health pushed to Notion
- [ ] 10. Daily digest email/push notification — morning summary delivered to phone or email without opening anything

## Notes
- LinkedIn, Indeed, Glassdoor are out of scope — ToS violations and bot detection
- Role expiry never touches opportunities beyond Qualification/Prioritized stage
- Discovery mode should flag new companies for David Thomas network check before auto-assigning Tier
