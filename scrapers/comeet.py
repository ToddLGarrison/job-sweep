"""
Comeet scraper.

Comeet embeds all positions as a JSON blob (COMPANY_POSITIONS_DATA) in a
<script> tag on the company job board page:
  https://www.comeet.com/jobs/{company_slug}/{company_token}

The ATS Slug stored in Notion is "{company_slug}/{company_token}" (e.g.
"cyera/17.008").
"""
import html
import json
import re

import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-sweep-bot/1.0)"}

# ISO-3166-1 alpha-2 → full name, for countries we expect to see in ATS data.
# Only non-US entries needed; US positions use city/state directly.
_COUNTRY_NAMES: dict[str, str] = {
    "CA": "Canada",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "NL": "Netherlands",
    "SE": "Sweden",
    "DK": "Denmark",
    "NO": "Norway",
    "FI": "Finland",
    "CH": "Switzerland",
    "AT": "Austria",
    "BE": "Belgium",
    "ES": "Spain",
    "IT": "Italy",
    "PT": "Portugal",
    "IE": "Ireland",
    "PL": "Poland",
    "CZ": "Czech Republic",
    "HU": "Hungary",
    "RO": "Romania",
    "TR": "Turkey",
    "IL": "Israel",
    "AU": "Australia",
    "NZ": "New Zealand",
    "SG": "Singapore",
    "JP": "Japan",
    "IN": "India",
    "CN": "China",
    "TW": "Taiwan",
    "KR": "South Korea",
    "BR": "Brazil",
    "MX": "Mexico",
    "PK": "Pakistan",
    "BD": "Bangladesh",
    "LK": "Sri Lanka",
    "NP": "Nepal",
    "VN": "Vietnam",
    "ID": "Indonesia",
    "PH": "Philippines",
    "ZA": "South Africa",
    "NG": "Nigeria",
    "EG": "Egypt",
}


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    url = f"https://www.comeet.com/jobs/{slug}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [Comeet/{slug}]: {e}")
        return [], 0

    try:
        positions = _parse_positions(resp.text)
    except Exception as e:
        print(f"ERROR [Comeet/{slug}] parse failure: {e}")
        return [], 0

    results = []
    geo_filtered = 0

    for pos in positions:
        title = pos.get("name", "").strip()
        apply_url = pos.get("url_active_page", "") or pos.get("url_comeet_hosted_page", "")
        if not title or not apply_url:
            continue

        location = _extract_location(pos.get("location", {}))

        if not is_us_or_remote(location):
            geo_filtered += 1
            continue

        if is_title_geo_excluded(title):
            geo_filtered += 1
            continue

        description = _extract_description(pos)
        results.append(JobListing(
            title=title,
            url=apply_url,
            location=location,
            description=description,
        ))

    return results, geo_filtered


def _parse_positions(page_html: str) -> list[dict]:
    """Extract the COMPANY_POSITIONS_DATA JSON array from the page."""
    m = re.search(r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\]);\s*\n", page_html, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Fallback: broader match
    m = re.search(r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*\]);", page_html, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError("COMPANY_POSITIONS_DATA not found in page")


def _extract_location(loc: dict) -> str:
    """Build a location string from a Comeet location object."""
    if not loc:
        return ""

    country_code = (loc.get("country") or "").strip()
    city = (loc.get("city") or "").strip()
    state = (loc.get("state") or "").strip()
    is_remote = loc.get("is_remote", False)

    if country_code == "US":
        if city and state:
            return f"{city}, {state}"
        if city:
            return city
        if is_remote:
            return "Remote"
        return "United States"

    # Non-US — resolve country code to full name for geo filter
    country_name = _COUNTRY_NAMES.get(country_code, country_code)

    if is_remote and not city:
        # Fully remote but geo-restricted to a non-US country
        return country_name

    if city and country_name:
        return f"{city}, {country_name}"

    return country_name or city


def _extract_description(pos: dict) -> str:
    parts = []
    for detail in pos.get("custom_fields", {}).get("details", []):
        text = detail.get("value", "")
        if text:
            parts.append(_strip_html(text))
    return " ".join(parts)


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text))
