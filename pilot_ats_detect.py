#!/usr/bin/env python3
"""
pilot_ats_detect.py — ATS enrichment for Companies with no ATS set.

Per company:
  - Always writes Last Enrichment Attempt (today's date).
  - High-confidence + ATS Slug empty  → writes ATS and ATS Slug.
  - High-confidence + ATS Slug exists → flags as conflict, no overwrite.
  - Low-confidence or not found       → no ATS/ATS Slug write.
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

# Workday CDN/asset path segments that appear before the real board name in Workday page HTML.
# Workday tenant subdomains serve JS/CSS under paths like /en-US/assets/... or /en-US/a/...
# which share the same URL structure as the real board URL but are NOT the board name.
_WD_INVALID_BOARDS = frozenset({"assets", "js", "css", "fonts", "img", "images", "static", "wday", "en"})

# Jobvite CDN asset paths that match the company-handle slot but are not company handles.
_JOBVITE_INVALID_SLUGS = frozenset({"__assets__", "assets", "static", "cdn"})

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
    # Workday — job posting URL: board name is the segment immediately before /job/
    # This pattern cannot hit CDN asset paths (which never contain /job/).
    (
        re.compile(r'([a-z0-9\-]+\.wd\d+)\.myworkdayjobs\.com/[^/]*/([A-Za-z0-9_][A-Za-z0-9_\-]+)/job/', re.I),
        "Workday", "high",
        lambda m: f"{m.group(1).lower()}/{m.group(2)}",
    ),
    # Workday — board root URL fallback (no /job/ required); board name ≥2 chars required.
    # CDN paths with single-letter or known asset segment names are caught by _WD_INVALID_BOARDS
    # guard in _scan_text and downgraded to low-confidence.
    (
        re.compile(r'([a-z0-9\-]+\.wd\d+)\.myworkdayjobs\.com/[^/]*/([A-Za-z0-9_][A-Za-z0-9_\-]+)', re.I),
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
_PILOT_TIER1_MAX = 500
_PILOT_TIER2_MAX = 500
_PILOT_TIER3_MAX = 500


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
            existing_slug = "".join(
                t.get("plain_text", "")
                for t in props.get("ATS Slug", {}).get("rich_text", [])
            ).strip()
            rows.append({
                "page_id": page["id"], "name": name, "tier": tier,
                "website": website, "existing_slug": existing_slug,
            })
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


def write_ats_detection(page_id: str, ats: str, slug: str) -> None:
    _notion.pages.update(
        page_id=page_id,
        properties={
            "ATS": {"select": {"name": ats}},
            "ATS Slug": {"rich_text": [{"text": {"content": slug}}]},
        },
    )


# ---------------------------------------------------------------------------
# ATS detection
# ---------------------------------------------------------------------------

def _is_guarded(ats: str, slug: str, m: re.Match) -> bool:
    """Return True if this match should be rejected as a CDN artifact or generic path."""
    if ats == "Greenhouse" and slug in _GH_GENERIC_SLUGS:
        return True
    if ats == "Workday":
        board = m.group(2)
        if board.lower() in _WD_INVALID_BOARDS or board.startswith("__"):
            return True
    if ats == "Jobvite" and (slug.startswith("__") or slug in _JOBVITE_INVALID_SLUGS):
        return True
    return False


def _scan_text(text: str) -> tuple[str, str, str] | None:
    """
    Return (ats, slug, confidence) from the first unguarded pattern match, or None.

    For each pattern, iterate ALL occurrences so that a CDN artifact earlier in the
    HTML doesn't shadow a real company handle that appears later on the same page.
    If every occurrence is guarded, return the first as low-confidence (so the caller
    knows the ATS was detected but the slug is untrustworthy).
    """
    for pattern, ats, confidence, extractor in _ATS_PATTERNS:
        first_guarded: tuple[str, str, str] | None = None
        pos = 0
        while True:
            m = pattern.search(text, pos)
            if not m:
                break
            slug = extractor(m)
            if _is_guarded(ats, slug, m):
                if first_guarded is None:
                    first_guarded = (ats, slug, "low")
                pos = m.end()
                continue
            return ats, slug, confidence  # clean match
        if first_guarded is not None:
            return first_guarded  # all matches were guarded; return first as low-confidence
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
    print("Fetching companies from Notion (ATS=null, Website set, not yet attempted)…")
    companies = fetch_candidates(_PILOT_TIER1_MAX, _PILOT_TIER2_MAX, _PILOT_TIER3_MAX)
    n1 = sum(1 for c in companies if "1" in c["tier"])
    n2 = sum(1 for c in companies if "2" in c["tier"])
    n3 = len(companies) - n1 - n2
    print(f"Sample: {len(companies)} companies  (Tier 1: {n1}, Tier 2: {n2}, Tier 3: {n3})\n")

    results = []
    run_start = time.monotonic()
    conflicts: list[dict] = []   # pre-existing ATS Slug conflicts

    # Outcome counters
    auto_written = 0
    held_for_review = 0
    not_found_count = 0
    low_conf_count = 0

    col_w = 44
    print(f"{'Company':<{col_w}} {'ATS':<16} {'Slug':<36} {'Conf':<6} {'Written':<10} {'s':>5}")
    print("-" * (col_w + 16 + 36 + 6 + 10 + 7))

    for c in companies:
        ats, slug, conf, elapsed = detect_ats(c["website"])

        tier_short = c["tier"].split("–")[0].strip() if "–" in c["tier"] else c["tier"]
        name_display = f"{c['name']} [{tier_short}]"
        slug_display = slug[:34] if slug else "—"
        conf_display = f"[{conf}]" if conf else ""

        written_label = ""
        if conf == "high" and ats != "not found":
            if not c["existing_slug"]:
                try:
                    write_ats_detection(c["page_id"], ats, slug)
                    written_label = "✓ written"
                    auto_written += 1
                except Exception as e:
                    written_label = "ERR"
                    print(f"  WARNING: could not write ATS for {c['name']}: {e}")
            else:
                written_label = "⚠ conflict"
                held_for_review += 1
                conflicts.append({
                    "name": c["name"],
                    "detected_ats": ats,
                    "detected_slug": slug,
                    "existing_slug": c["existing_slug"],
                    "website": c["website"],
                })
        elif ats == "not found":
            not_found_count += 1
        else:
            low_conf_count += 1

        print(f"{name_display:<{col_w}} {ats:<16} {slug_display:<36} {conf_display:<6} {written_label:<10} {elapsed:>5.1f}s")

        try:
            write_enrichment_attempt(c["page_id"])
        except Exception as e:
            print(f"  WARNING: could not write Last Enrichment Attempt for {c['name']}: {e}")

        results.append({**c, "ats": ats, "slug": slug, "conf": conf, "elapsed": elapsed})
        time.sleep(0.3)

    run_elapsed = time.monotonic() - run_start

    print()
    print("=" * 80)
    avg = run_elapsed / len(results) if results else 0
    print(f"Run complete:    {len(results)} companies checked in {run_elapsed:.1f}s ({avg:.1f}s avg)")
    print(f"Auto-written:    {auto_written}  (ATS + ATS Slug written to Notion)")
    print(f"Held for review: {held_for_review}  (high-confidence but ATS Slug already had text — see conflicts below)")
    print(f"Low-confidence:  {low_conf_count}  (Gem, Indeed, or generic slug — not written)")
    print(f"Not found:       {not_found_count}")

    if conflicts:
        print()
        print("PRE-EXISTING ATS SLUG CONFLICTS (needs manual review):")
        print("  Script detected one ATS but company already had text in ATS Slug field.")
        for cx in conflicts:
            print(f"  {cx['name']}")
            print(f"    Detected:    {cx['detected_ats']}  slug={cx['detected_slug']!r}")
            print(f"    Existing:    {cx['existing_slug']!r}")
            print(f"    Website:     {cx['website']}")

    low_results = [r for r in results if r["conf"] == "low" and r["ats"] != "not found"]
    if low_results:
        print()
        print("LOW-CONFIDENCE (not written — verify manually):")
        for r in low_results:
            print(f"  {r['name']}: {r['ats']} slug={r['slug']!r}  {r['website']}")


if __name__ == "__main__":
    main()
