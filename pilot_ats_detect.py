#!/usr/bin/env python3
"""
pilot_ats_detect.py — ATS detection pilot for Companies with no ATS set.

Writes "Last Enrichment Attempt" (date) to every company checked.
Does NOT write ATS or ATS Slug — those are set manually after review.
Run: python pilot_ats_detect.py
"""
import datetime
import re
import time
from urllib.parse import urlparse

import requests
from notion_client import Client

from config import COMPANIES_DB_ID, NOTION_API_KEY

# ---------------------------------------------------------------------------
# ATS detection: (regex, ats_name, confidence, slug_extractor)
# Slug extractor receives the re.Match and returns the slug string the
# existing scrapers expect in the "ATS Slug" Notion field.
# ---------------------------------------------------------------------------

# Greenhouse board tokens that are generic widget paths, not real board names.
_GH_GENERIC_SLUGS = {"embed", "jobs", "boards", "widget", "careers", "search", "apply", "api"}

_ATS_PATTERNS = [
    # Greenhouse — two URL formats
    (
        re.compile(r'boards\.greenhouse\.io/([A-Za-z0-9_\-]+)', re.I),
        "Greenhouse", "high",
        lambda m: m.group(1).lower(),
    ),
    (
        re.compile(r'job-boards\.greenhouse\.io/([A-Za-z0-9_\-]+)', re.I),
        "Greenhouse", "high",
        lambda m: m.group(1).lower(),
    ),
    # Lever
    (
        re.compile(r'jobs\.lever\.co/([A-Za-z0-9_\-]+)', re.I),
        "Lever", "high",
        lambda m: m.group(1).lower(),
    ),
    # Ashby
    (
        re.compile(r'jobs\.ashbyhq\.com/([A-Za-z0-9_\-]+)', re.I),
        "Ashby", "high",
        lambda m: m.group(1).lower(),
    ),
    # Workday: slug = "tenant.wdN/board"
    (
        re.compile(r'([a-z0-9\-]+\.wd\d+)\.myworkdayjobs\.com/[^/]*/([A-Za-z0-9_\-]+)', re.I),
        "Workday", "high",
        lambda m: f"{m.group(1).lower()}/{m.group(2)}",
    ),
    # Workable
    (
        re.compile(r'apply\.workable\.com/([A-Za-z0-9_\-]+)', re.I),
        "Workable", "high",
        lambda m: m.group(1).lower(),
    ),
    # Rippling ATS
    (
        re.compile(r'ats\.rippling\.com/([A-Za-z0-9_\-]+)', re.I),
        "Rippling", "high",
        lambda m: m.group(1).lower(),
    ),
    # SmartRecruiters
    (
        re.compile(r'careers\.smartrecruiters\.com/([A-Za-z0-9_\-]+)', re.I),
        "SmartRecruiters", "high",
        lambda m: m.group(1),
    ),
    (
        re.compile(r'smartrecruiters\.com/([A-Za-z0-9_\-]+)/postings', re.I),
        "SmartRecruiters", "high",
        lambda m: m.group(1),
    ),
    # Jobvite
    (
        re.compile(r'jobs\.jobvite\.com/([A-Za-z0-9_\-]+)', re.I),
        "Jobvite", "high",
        lambda m: m.group(1).lower(),
    ),
    # comeet: slug is "company_slug/token"
    (
        re.compile(r'comeet\.com/jobs/([A-Za-z0-9_\-]+/[A-Za-z0-9._\-]+)', re.I),
        "comeet", "high",
        lambda m: m.group(1),
    ),
    # iCIMS: subdomain is "careers-{slug}"
    (
        re.compile(r'careers-([A-Za-z0-9_\-]+)\.icims\.com', re.I),
        "iCIMS", "high",
        lambda m: m.group(1).lower(),
    ),
    # Recruitee: subdomain is the slug
    (
        re.compile(r'([A-Za-z0-9_\-]+)\.recruitee\.com', re.I),
        "Recruitee", "high",
        lambda m: m.group(1).lower(),
    ),
    # Work at a Startup (YC)
    (
        re.compile(r'workatastartup\.com/companies/([A-Za-z0-9_\-]+)', re.I),
        "WorkAtAStartup", "high",
        lambda m: m.group(1).lower(),
    ),
    # BambooHR
    (
        re.compile(r'([A-Za-z0-9_\-]+)\.bamboohr\.com/careers', re.I),
        "BambooHR", "high",
        lambda m: m.group(1).lower(),
    ),
    # Low-confidence: Gem and Indeed — flag only
    (
        re.compile(r'app\.gem\.com', re.I),
        "Gem", "low",
        lambda m: "",
    ),
    (
        re.compile(r'indeed\.com/cmp/([A-Za-z0-9_\-]+)', re.I),
        "Indeed", "low",
        lambda m: m.group(1).lower(),
    ),
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10
_FALLBACK_PATHS = ["/careers", "/jobs"]   # two paths only, max ~30s worst-case per company
_PILOT_TIER1_MAX = 20
_PILOT_TIER2_MAX = 35
_PILOT_TIER3_MAX = 15


# ---------------------------------------------------------------------------
# Notion helpers
# ---------------------------------------------------------------------------

_notion = Client(auth=NOTION_API_KEY)
_TODAY = datetime.date.today().isoformat()


def fetch_candidates(limit_tier1: int, limit_tier2: int, limit_tier3: int) -> list[dict]:
    """
    Return companies where ATS is empty, Website is set, and
    Last Enrichment Attempt is empty — sorted Tier 1 first.
    """
    rows = []
    cursor = None
    while True:
        kwargs: dict = {
            "filter": {
                "and": [
                    {"property": "ATS", "select": {"is_empty": True}},
                    {"property": "Website", "url": {"is_not_empty": True}},
                    {"property": "Last Enrichment Attempt", "date": {"is_empty": True}},
                ]
            }
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _notion.data_sources.query(COMPANIES_DB_ID, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            name = "".join(t.get("plain_text", "") for t in props.get("Name", {}).get("title", []))
            tier = (props.get("Tier", {}).get("select") or {}).get("name", "")
            website = props.get("Website", {}).get("url") or ""
            if not website:
                continue
            rows.append({"page_id": page["id"], "name": name, "tier": tier, "website": website})
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    rows.sort(key=lambda r: 0 if "1" in r["tier"] else (1 if "2" in r["tier"] else 2))

    tier1 = [r for r in rows if "1" in r["tier"]][:limit_tier1]
    tier2 = [r for r in rows if "2" in r["tier"]][:limit_tier2]
    tier3 = [r for r in rows if "2" not in r["tier"] and "1" not in r["tier"]][:limit_tier3]
    return tier1 + tier2 + tier3


def write_enrichment_attempt(page_id: str) -> None:
    _notion.pages.update(
        page_id=page_id,
        properties={"Last Enrichment Attempt": {"date": {"start": _TODAY}}},
    )


# ---------------------------------------------------------------------------
# ATS detection
# ---------------------------------------------------------------------------

def _scan_text(text: str) -> tuple[str, str, str] | None:
    """Return (ats, slug, confidence) from the first pattern match, or None."""
    for pattern, ats, confidence, extractor in _ATS_PATTERNS:
        m = pattern.search(text)
        if m:
            slug = extractor(m)
            # Greenhouse slug guard: generic widget paths are not real board tokens
            if ats == "Greenhouse" and slug in _GH_GENERIC_SLUGS:
                return ats, slug, "low"
            return ats, slug, confidence
    return None


def detect_ats(website: str) -> tuple[str, str, str, float]:
    """
    Fetch website + up to 2 fallback paths. Return (ats, slug, confidence, elapsed_s).
    ats="not found" when nothing matches.
    """
    t0 = time.monotonic()

    def _fetch(url: str):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
            for r in resp.history:
                hit = _scan_text(r.url)
                if hit:
                    return hit
            hit = _scan_text(resp.url)
            if hit:
                return hit
            return _scan_text(resp.text)
        except Exception:
            return None

    result = _fetch(website)
    if result:
        ats, slug, conf = result
        return ats, slug, conf, time.monotonic() - t0

    parsed = urlparse(website.rstrip("/"))
    base_origin = f"{parsed.scheme}://{parsed.netloc}"
    for path in _FALLBACK_PATHS:
        result = _fetch(base_origin + path)
        if result:
            ats, slug, conf = result
            return ats, slug, conf, time.monotonic() - t0

    return "not found", "", "", time.monotonic() - t0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Fetching pilot companies from Notion…")
    companies = fetch_candidates(_PILOT_TIER1_MAX, _PILOT_TIER2_MAX, _PILOT_TIER3_MAX)
    print(f"Pilot sample: {len(companies)} companies  "
          f"(Tier 1: {sum(1 for c in companies if '1' in c['tier'])}, "
          f"Tier 2: {sum(1 for c in companies if '2' in c['tier'])}, "
          f"Tier 3: {sum(1 for c in companies if '2' not in c['tier'] and '1' not in c['tier'])})\n")

    results = []
    pilot_start = time.monotonic()
    timeouts = []

    col_w = 44
    print(f"{'Company':<{col_w}} {'ATS':<16} {'Slug':<36} {'Conf':<6} {'s':>5}")
    print("-" * (col_w + 16 + 36 + 6 + 6 + 4))

    for c in companies:
        ats, slug, conf, elapsed = detect_ats(c["website"])

        tier_short = c["tier"].split("–")[0].strip() if "–" in c["tier"] else c["tier"]
        name_display = f"{c['name']} [{tier_short}]"
        slug_display = slug[:34] if slug else "—"
        conf_display = f"[{conf}]" if conf else ""
        print(f"{name_display:<{col_w}} {ats:<16} {slug_display:<36} {conf_display:<6} {elapsed:>5.1f}s")

        if elapsed >= _TIMEOUT * 2:
            timeouts.append(c["name"])

        try:
            write_enrichment_attempt(c["page_id"])
        except Exception as e:
            print(f"  WARNING: could not write Last Enrichment Attempt for {c['name']}: {e}")

        results.append({**c, "ats": ats, "slug": slug, "conf": conf, "elapsed": elapsed})
        time.sleep(0.3)

    pilot_elapsed = time.monotonic() - pilot_start
    found = [r for r in results if r["ats"] != "not found"]
    high_conf = [r for r in found if r["conf"] == "high"]
    low_conf = [r for r in found if r["conf"] == "low"]

    print()
    print("=" * 80)
    print(f"Pilot complete:  {len(found)}/{len(results)} detected  "
          f"({len(high_conf)} high-confidence, {len(low_conf)} low-confidence)")
    print(f"Pilot runtime:   {pilot_elapsed:.1f}s total  "
          f"({pilot_elapsed/len(results):.1f}s avg/company)")

    if timeouts:
        non_timeout_times = [r["elapsed"] for r in results if r["name"] not in timeouts]
        avg_non = sum(non_timeout_times) / len(non_timeout_times) if non_timeout_times else 0
        print(f"Timeouts:        {len(timeouts)} companies  "
              f"(avg ex-timeout: {avg_non:.1f}s)")

    total_remaining = 245 - 20 - len(results)
    avg = pilot_elapsed / len(results)
    extrapolated = avg * (245 - 20)
    print(f"Extrapolation:   ~{extrapolated/60:.0f} min for remaining {245-20} companies "
          f"({extrapolated:.0f}s at {avg:.1f}s avg)")

    if low_conf:
        print()
        print("LOW-CONFIDENCE / GENERIC SLUG (verify manually before adding to Notion):")
        for r in low_conf:
            print(f"  {r['name']}: {r['ats']} slug={r['slug']!r}  {r['website']}")

    if high_conf:
        print()
        print("HIGH-CONFIDENCE DETECTIONS (ready to add to Notion):")
        for r in high_conf:
            print(f"  {r['name']}: {r['ats']}  slug={r['slug']!r}")


if __name__ == "__main__":
    main()
