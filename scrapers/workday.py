import re

import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible)",
}
_LIMIT = 20

# Workday uses 3-letter ISO country codes in two formats:
#   "USA - CA - Remote"  (code-first, dash-separated)
#   "Bengaluru, IND"     (city-first, code at end)
_WD_CODE_FIRST_RE = re.compile(r"^([A-Z]{2,3})\s*-\s*(.+)$")
_WD_CODE_LAST_RE = re.compile(r"^.+,\s*([A-Z]{3})$")


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    if "/" not in slug:
        print(f"ERROR [Workday/{slug}]: malformed slug — expected 'tenant.wdN/BoardName'")
        return [], 0
    subdomain, board = slug.split("/", 1)
    # tenant in the API path is the subdomain without the .wd{N} version suffix
    tenant = subdomain.split(".")[0]
    url = f"https://{subdomain}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"

    results = []
    geo_filtered = 0
    offset = 0

    while True:
        payload = {"appliedFacets": {}, "limit": _LIMIT, "offset": offset, "searchText": ""}
        try:
            resp = requests.post(url, json=payload, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"ERROR [Workday/{slug}]: {e}")
            return [], 0

        postings = data.get("jobPostings", [])
        total = data.get("total", 0)

        for posting in postings:
            title = (posting.get("title") or "").strip()
            external_path = (posting.get("externalPath") or "").strip()
            if not title or not external_path:
                continue

            apply_url = f"https://{subdomain}.myworkdayjobs.com/en-US/{board}{external_path}"
            raw_loc = posting.get("locationsText") or ""

            # Workday uses country codes in two formats. Reject non-USA codes before the
            # generic geo filter, which defaults to "pass" for unrecognized strings.
            m_first = _WD_CODE_FIRST_RE.match(raw_loc)
            m_last = _WD_CODE_LAST_RE.match(raw_loc)
            if m_first and m_first.group(1) != "USA":
                geo_filtered += 1
                continue
            if m_last and m_last.group(1) not in ("USA", "UNK"):
                geo_filtered += 1
                continue

            location = _clean_location(raw_loc)
            if not is_us_or_remote(location):
                geo_filtered += 1
                continue

            if is_title_geo_excluded(title):
                geo_filtered += 1
                continue

            results.append(JobListing(title=title, url=apply_url, location=location))

        offset += len(postings)
        if not postings or offset >= total:
            break

    return results, geo_filtered


def _clean_location(loc: str) -> str:
    """Normalize Workday locationsText for geo filtering.

    Workday formats locations as "{COUNTRY_CODE} - {detail}" (e.g. "USA - CA - Remote",
    "IND - Bengaluru"). We convert these to strings the geo filter understands.
    Multi-location strings like "44 Locations" are left empty so they pass through.
    """
    if not loc:
        return ""

    m = _WD_CODE_FIRST_RE.match(loc)
    if m:
        country_code, detail = m.group(1), m.group(2).strip()
        if country_code == "USA":
            # "USA - CA - Remote" → "Remote"; "USA - CA - San Francisco" → "San Francisco, CA"
            parts = [p.strip() for p in detail.split("-")]
            if any("remote" in p.lower() for p in parts):
                return "Remote"
            # Last part is city, first part is state
            if len(parts) >= 2:
                return f"{parts[-1]}, {parts[0]}"
            return parts[0] or "United States"
        # Non-US country code → return the raw code as the location so geo filter rejects it
        return loc

    # "N Locations" multi-location string → no reliable geo signal
    if re.match(r"^\d+ Locations?$", loc):
        return ""

    # Standard "City, State, United States" format — strip trailing country
    if loc.endswith(", United States"):
        return loc[: -len(", United States")]

    return loc
