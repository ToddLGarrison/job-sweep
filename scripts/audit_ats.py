#!/usr/bin/env python3
"""
Audit the Notion Companies database for missing, blank, or incorrect ATS values.

For every company record:
  - Flags blank ATS, blank slug, unknown ATS value, or YC-as-ATS
  - Attempts ATS detection via careers URL resolution, page HTML scan,
    and slug-derived board URL HEAD checks
  - Assigns confidence: HIGH (URL pattern), MEDIUM (HTML signal), N/A

Output:
  stdout                       actionable records only (UPDATE ATS / UPDATE SLUG /
                               VERIFY / ERROR), sorted by priority then name
  scripts/ats_audit_report.txt all records including OK, same sort order

Usage:
    python scripts/audit_ats.py
"""
import contextlib
import datetime
import io
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests as req_lib
from notion_client import Client
from notion_client.errors import APIResponseError, RequestTimeoutError

from config import ATS_SCRAPER_MAP, COMPANIES_DB_ID, NOTION_API_KEY
from scrapers.ats_detector import resolve_ats

_notion = Client(auth=NOTION_API_KEY, timeout_ms=30_000)
_MAX_RETRIES = 3
_HTTP_TIMEOUT = 15
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

KNOWN_ATS = set(ATS_SCRAPER_MAP.keys())

_ACTION_ORDER = {
    "UPDATE ATS": 0,
    "UPDATE SLUG": 1,
    "VERIFY": 2,
    "ERROR": 3,
    "OK": 4,
}

# ATS domain signals for page HTML href/src scan (MEDIUM confidence)
_HTML_SIGNALS: list[tuple[str, str]] = [
    ("Greenhouse", "greenhouse.io"),
    ("Lever", "lever.co"),
    ("Ashby", "ashbyhq.com"),
    ("Workday", "myworkdayjobs.com"),
    ("SmartRecruiters", "smartrecruiters.com"),
    ("Workable", "apply.workable.com"),
    ("comeet", "comeet.com"),
    ("icims", "icims.com"),
    ("Rippling", "ats.rippling.com"),
    ("Jobvite", "jobs.jobvite.com"),
    ("BambooHR", "bamboohr.com"),
    ("Recruitee", "recruitee.com"),
    ("Gem", "hire.gem.com"),
]

# Slug-derived board URLs for HEAD verification.
# Only used for flagged companies (blank/unknown ATS) that have no careers URL.
# BambooHR omitted — slug goes in subdomain, not path; cannot be checked generically.
_SLUG_BOARD_CHECKS: list[tuple[str, str]] = [
    ("Greenhouse", "https://boards.greenhouse.io/{slug}"),
    ("Lever", "https://jobs.lever.co/{slug}"),
    ("Ashby", "https://jobs.ashbyhq.com/{slug}"),
    ("SmartRecruiters", "https://jobs.smartrecruiters.com/{slug}"),
    ("Workable", "https://apply.workable.com/{slug}/"),
    ("Rippling", "https://ats.rippling.com/{slug}/jobs"),
    ("Jobvite", "https://jobs.jobvite.com/{slug}/feed"),
]


# ── Notion helpers ──────────────────────────────────────────────────────────────

def _call_notion(fn, *args, **kwargs):
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except RequestTimeoutError:
            if attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)
        except APIResponseError as e:
            if e.status == 429 and attempt < _MAX_RETRIES - 1:
                time.sleep(5 * (2 ** attempt))
                continue
            raise


def _get_title(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("title", []))


def _get_select(prop: dict) -> str:
    sel = prop.get("select")
    return sel["name"] if sel else ""


def _get_text(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))


def _find_careers_url(props: dict) -> str:
    """Read a URL from the first matching Notion property name."""
    for name in ("Careers URL", "Website", "URL"):
        if name not in props:
            continue
        p = props[name]
        val = p.get("url") or ""
        if val:
            return val
        val = _get_text(p)
        if val:
            return val
    return ""


def fetch_all_companies() -> list[dict]:
    """Return every company page from Notion, including records with blank ATS or slug."""
    companies: list[dict] = []
    cursor = None
    while True:
        kwargs: dict = {}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _call_notion(_notion.data_sources.query, COMPANIES_DB_ID, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            companies.append({
                "page_id": page["id"],
                "name": _get_title(props.get("Name", {})),
                "ats": _get_select(props.get("ATS", {})),
                "ats_slug": _get_text(props.get("ATS Slug", {})),
                "careers_url": _find_careers_url(props),
            })
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return companies


# ── ATS Detection ───────────────────────────────────────────────────────────────

def _scan_html_for_ats(html: str) -> str | None:
    """Scan page HTML href/src attributes for ATS domain signals."""
    link_re = re.compile(r'(?:href|src)=["\']([^"\']{4,})["\']', re.IGNORECASE)
    found = " ".join(link_re.findall(html)).lower()
    for ats_name, domain in _HTML_SIGNALS:
        if domain in found:
            return ats_name
    return None


def _try_slug_boards(slug: str) -> str | None:
    """HEAD each known board URL for this slug. Returns ATS name on 200, else None."""
    for ats_name, template in _SLUG_BOARD_CHECKS:
        url = template.format(slug=slug)
        try:
            r = req_lib.head(url, timeout=8, allow_redirects=True, headers=_HEADERS)
            if r.status_code == 200:
                return ats_name
        except Exception:
            continue
    return None


def _resolve_ats_quiet(url: str) -> tuple[str, str] | None:
    """Call resolve_ats() suppressing its stdout redirect-resolution prints."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = resolve_ats(url)
    if result and buf.getvalue().strip():
        # Surface redirect resolution as a note via stderr so it's visible but not in report
        print(f"    redirect: {buf.getvalue().strip()}", file=sys.stderr)
    return result


def detect_ats_for_company(
    careers_url: str, ats_slug: str, ats_is_flagged: bool
) -> tuple[str, str, str]:
    """
    Returns (detected_ats, confidence, error_note).

    Pass 1+2  careers URL → resolve_ats() (URL pattern + redirect following) → HIGH
    Pass 3    careers URL → fetch page HTML, scan links/scripts for ATS signals → MEDIUM
    Pass 4    slug → HEAD each known board URL (only for flagged companies) → HIGH
    """
    if careers_url:
        # Pass 1+2: URL pattern match, with redirect following
        try:
            result = _resolve_ats_quiet(careers_url)
            if result:
                return result[0], "HIGH", ""
        except Exception:
            pass

        # Pass 3: page HTML content scan
        try:
            resp = req_lib.get(
                careers_url, timeout=_HTTP_TIMEOUT,
                allow_redirects=True, headers=_HEADERS,
            )
            if resp.status_code == 200:
                found = _scan_html_for_ats(resp.text)
                if found:
                    return found, "MEDIUM", ""
                return "UNKNOWN", "N/A", ""
            return "UNKNOWN", "N/A", f"HTTP {resp.status_code}"
        except req_lib.exceptions.Timeout:
            return "UNKNOWN", "N/A", "fetch timeout"
        except Exception as e:
            return "UNKNOWN", "N/A", f"fetch error: {type(e).__name__}"

    # Pass 4: slug-derived board URL HEAD check (flagged companies only — avoids
    # hammering board APIs for every OK company that has no careers URL set)
    if ats_is_flagged and ats_slug:
        found = _try_slug_boards(ats_slug)
        if found:
            return found, "HIGH", "detected via slug board URL"
        return "UNKNOWN", "N/A", "slug board check inconclusive"

    return "N/A", "N/A", ""


# ── Classification ──────────────────────────────────────────────────────────────

def classify(company: dict) -> dict:
    name = company["name"]
    ats = company["ats"]
    slug = company["ats_slug"]
    careers_url = company["careers_url"]

    ats_is_flagged = not ats or ats not in KNOWN_ATS

    try:
        detected, confidence, error_note = detect_ats_for_company(
            careers_url, slug, ats_is_flagged
        )
    except Exception as e:
        return {
            **company,
            "action": "ERROR",
            "detected_ats": "ERROR",
            "confidence": "N/A",
            "error_note": str(e),
        }

    if not ats or ats not in KNOWN_ATS:
        action = "UPDATE ATS"
    elif not slug:
        action = "UPDATE SLUG"
    elif (
        detected not in ("UNKNOWN", "N/A", "ERROR")
        and detected.lower() != ats.lower()
    ):
        action = "VERIFY"
    else:
        action = "OK"

    return {
        **company,
        "action": action,
        "detected_ats": detected,
        "confidence": confidence,
        "error_note": error_note,
    }


# ── Formatting ──────────────────────────────────────────────────────────────────

def format_record(r: dict) -> str:
    url_display = r["careers_url"] or "NOT SET"
    if r["error_note"]:
        url_display += f"  [{r['error_note']}]"
    return "\n".join([
        f"Company: {r['name'] or '(unnamed)'}",
        f"Current ATS: {r['ats'] or 'BLANK'}",
        f"Current Slug: {r['ats_slug'] or 'BLANK'}",
        f"Detected ATS: {r['detected_ats']}",
        f"Confidence: {r['confidence']}",
        f"Careers URL: {url_display}",
        f"Action needed: {r['action']}",
        "---",
    ])


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Fetching all companies from Notion...", file=sys.stderr)
    companies = fetch_all_companies()
    total = len(companies)
    print(f"Found {total} records. Running detection...\n", file=sys.stderr)

    results: list[dict] = []
    for i, company in enumerate(companies, 1):
        print(f"  [{i}/{total}] {company['name']}", file=sys.stderr)
        results.append(classify(company))

    print("", file=sys.stderr)

    results.sort(key=lambda r: (
        _ACTION_ORDER.get(r["action"], 99),
        (r["name"] or "").lower(),
    ))

    counts: dict[str, int] = {"UPDATE ATS": 0, "UPDATE SLUG": 0, "VERIFY": 0, "OK": 0, "ERROR": 0}
    for r in results:
        counts[r["action"]] = counts.get(r["action"], 0) + 1

    today = datetime.date.today().isoformat()
    header = [f"ATS Audit Report — {today}", "=" * 50, ""]
    actionable = {"UPDATE ATS", "UPDATE SLUG", "VERIFY", "ERROR"}

    all_blocks: list[str] = []
    stdout_blocks: list[str] = []
    for r in results:
        block = format_record(r)
        all_blocks.append(block)
        if r["action"] in actionable:
            stdout_blocks.append(block)

    summary = [
        "",
        f"=== ATS Audit Summary — {today} ===",
        f"Total companies audited:     {total}",
        f"  OK (no action needed):     {counts['OK']}",
        f"  Update ATS needed:         {counts['UPDATE ATS']}",
        f"  Update Slug needed:        {counts['UPDATE SLUG']}",
        f"  Verify (mismatch):         {counts['VERIFY']}",
        f"  Detection error/timeout:   {counts['ERROR']}",
    ]

    report_path = Path(__file__).parent / "ats_audit_report.txt"
    report_path.write_text("\n".join(header + all_blocks + summary) + "\n")

    print("\n".join(header + stdout_blocks + summary))
    print(f"\nFull report (all companies including OK) written to: {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
