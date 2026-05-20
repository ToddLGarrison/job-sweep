"""Discovery scraper for Built In Boston job listings.

Flow per keyword:
  1. GET search listing page → parse job cards (title, company, Built In detail URL)
  2. For each card, GET detail page → extract howToApply URL from Builtin.jobPostInit JSON
  3. Run ATS detection on howToApply URL → skip if unknown ATS
  4. Return DiscoveryListing objects for recognized ATS jobs
"""
import json
import re
import time
from urllib.parse import quote

from curl_cffi import requests
from bs4 import BeautifulSoup

from models import DiscoveryListing
from scrapers.ats_detector import extract_ats_domain, resolve_ats

_BASE_URL = "https://www.builtinboston.com"
_SEARCH_URL = _BASE_URL + "/jobs?search={keyword}&remote=true"
_IMPERSONATE = "chrome120"
_REQUEST_DELAY = 1.0  # seconds between detail page fetches


def fetch_listings(keyword: str) -> tuple[list[DiscoveryListing], int]:
    url = _SEARCH_URL.format(keyword=quote(keyword))
    try:
        resp = requests.get(url, impersonate=_IMPERSONATE, timeout=20)
    except Exception as e:
        print(f"ERROR [BuiltInBoston] GET {url}: {e}")
        return [], 0

    if resp.status_code == 403:
        print(f"ERROR [BuiltInBoston] listing page blocked (403) for keyword '{keyword}' — skipping")
        return [], 0

    try:
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [BuiltInBoston] GET {url}: {e}")
        return [], 0

    cards = _parse_listing_page(resp.text)
    results = []
    unknown_ats = 0
    for company_name, title, detail_url in cards:
        try:
            apply_url = _fetch_apply_url(detail_url)
            time.sleep(_REQUEST_DELAY)  # polite delay only after a successful fetch
        except Exception as e:
            print(f"ERROR [BuiltInBoston] detail {detail_url}: {e}")
            continue

        if not apply_url:
            continue

        detected = resolve_ats(apply_url)
        if detected is None:
            domain = extract_ats_domain(apply_url)
            print(f"UNKNOWN ATS [BuiltInBoston] {company_name} | {title} | {domain}")
            unknown_ats += 1
            continue

        ats, slug = detected
        results.append(DiscoveryListing(
            title=title,
            url=apply_url,
            company_name=company_name,
            ats=ats,
            slug=slug,
        ))

    return results, unknown_ats


def _parse_listing_page(html: str) -> list[tuple[str, str, str]]:
    """Return list of (company_name, title, detail_url) from the listing page."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all(attrs={"data-id": "job-card"})
    results = []
    for card in cards:
        company_el = card.find(attrs={"data-id": "company-title"})
        company_name = company_el.get_text(strip=True) if company_el else ""

        title_el = card.find(attrs={"data-id": "job-card-title"})
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if not href:
            continue
        detail_url = (_BASE_URL + href) if href.startswith("/") else href

        results.append((company_name, title, detail_url))
    return results


def _fetch_apply_url(detail_url: str) -> str:
    """Fetch a Built In Boston job detail page and extract the howToApply URL."""
    resp = requests.get(detail_url, impersonate=_IMPERSONATE, timeout=20)
    resp.raise_for_status()
    return _extract_how_to_apply(resp.text)


def _extract_how_to_apply(html: str) -> str:
    """Parse howToApply URL from the Builtin.jobPostInit({...}) script block."""
    m = re.search(r"Builtin\.jobPostInit\((\{.*?\})\)", html, re.DOTALL)
    if not m:
        return ""
    try:
        data = json.loads(m.group(1))
        return data.get("job", {}).get("howToApply", "")
    except (json.JSONDecodeError, AttributeError):
        return ""
