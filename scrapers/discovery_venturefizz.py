"""Discovery scraper for VentureFizz job listings.

Flow per keyword:
  1. GET search listing page → parse job articles (title, VentureFizz detail URL)
  2. For each article, GET detail page → extract company name + ATS apply URL
  3. Run ATS detection on apply URL → skip if unknown ATS
  4. Return DiscoveryListing objects for recognized ATS jobs
"""
import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from models import DiscoveryListing
from scrapers.ats_detector import extract_ats_domain, resolve_ats

_SEARCH_URL = "https://venturefizz.com/jobs?q={keyword}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_REQUEST_DELAY = 0.5  # seconds between detail page fetches


def fetch_listings(
    keyword: str,
    seen_detail_urls: set[str] | None = None,
) -> tuple[list[DiscoveryListing], int]:
    url = _SEARCH_URL.format(keyword=quote(keyword))
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [VentureFizz] GET {url}: {e}")
        return [], 0

    job_cards = _parse_listing_page(resp.text)
    results = []
    unknown_ats = 0
    for title, detail_url in job_cards:
        if seen_detail_urls is not None:
            if detail_url in seen_detail_urls:
                continue
            seen_detail_urls.add(detail_url)
        try:
            time.sleep(_REQUEST_DELAY)
            company_name, apply_url = _fetch_detail(detail_url)
        except Exception as e:
            print(f"ERROR [VentureFizz] detail {detail_url}: {e}")
            continue

        if not apply_url:
            continue

        detected = resolve_ats(apply_url)
        if detected is None:
            domain = extract_ats_domain(apply_url)
            print(f"UNKNOWN ATS [VentureFizz] {company_name} | {title} | {domain}")
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


def _parse_listing_page(html: str) -> list[tuple[str, str]]:
    """Return list of (title, detail_url) from the VentureFizz listing page."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for article in soup.find_all("article", class_="job_listing"):
        h2 = article.find("h2", class_="job-title")
        if not h2:
            continue
        link = h2.find("a")
        if not link:
            continue
        title = link.get_text(strip=True)
        detail_url = link.get("href", "")
        if title and detail_url:
            results.append((title, detail_url))
    return results


def _fetch_detail(detail_url: str) -> tuple[str, str]:
    """Return (company_name, apply_url) from a VentureFizz job detail page."""
    resp = requests.get(detail_url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    return _parse_detail_page(resp.text)


def _parse_detail_page(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    company_name = _extract_company(soup)
    apply_url = _extract_apply_url(soup)

    return company_name, apply_url


def _extract_company(soup: BeautifulSoup) -> str:
    # Prefer JSON-LD hiringOrganization (most reliable)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and "hiringOrganization" in data:
                name = data["hiringOrganization"].get("name", "")
                if name:
                    return name
        except (json.JSONDecodeError, AttributeError):
            pass

    # Fallback: "<Job Title> at <Company> - VentureFizz" page title
    title_tag = soup.find("title")
    if title_tag:
        text = title_tag.get_text()
        if " at " in text:
            after_at = text.rsplit(" at ", 1)[-1]
            company = after_at.split(" - ")[0].strip()
            if company:
                return company

    # Fallback: employer link text
    employer = soup.find(class_=lambda c: c and "employer" in c.split())
    if employer:
        link = employer.find("a")
        if link:
            return link.get_text(strip=True)

    return ""


def _extract_apply_url(soup: BeautifulSoup) -> str:
    link = soup.select_one('a[class*="apply-job-external"]')
    if link:
        href = link.get("href", "")
        if href and href.startswith("http"):
            return href
    return ""
