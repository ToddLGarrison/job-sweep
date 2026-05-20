import re

import requests
from bs4 import BeautifulSoup

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

_SEARCH_URL = "https://careers-{slug}.icims.com/jobs/search?ss=1&searchKeyword=&pr={offset}&in_iframe=1"
_PAGE_SIZE = 20
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    # Notion slugs may be stored with a "careers-" prefix already (e.g. "careers-acme"),
    # which would double the prefix the URL template already adds.
    slug = slug.removeprefix("careers-")

    results = []
    geo_filtered = 0
    offset = 0

    while True:
        url = _SEARCH_URL.format(slug=slug, offset=offset)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"ERROR [iCIMS/{slug}]: {e}")
            return [], 0

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("li", class_="iCIMS_JobCardItem")

        for item in items:
            title_a = item.find("a", class_="iCIMS_Anchor")
            if not title_a:
                continue
            h3 = title_a.find("h3")
            title = h3.get_text(strip=True) if h3 else title_a.get_text(strip=True)
            job_url = title_a.get("href", "").split("?")[0]
            if not title or not job_url:
                continue

            location = _extract_location(item)

            if not is_us_or_remote(location):
                geo_filtered += 1
                continue

            if is_title_geo_excluded(title):
                geo_filtered += 1
                continue

            results.append(JobListing(title=title, url=job_url, location=location))

        total_pages = _parse_total_pages(soup)
        current_page = offset // _PAGE_SIZE + 1
        if current_page >= total_pages or not items:
            break
        offset += _PAGE_SIZE

    return results, geo_filtered


def _extract_location(item) -> str:
    loc_div = item.find("div", class_=lambda c: c and "header" in c and "left" in c)
    if not loc_div:
        return ""
    spans = loc_div.find_all("span")
    for span in spans:
        if "sr-only" not in (span.get("class") or []):
            return span.get_text(strip=True)
    return ""


def _parse_total_pages(soup) -> int:
    text = soup.get_text(separator=" ")
    m = re.search(r"Page\s+\d+\s+of\s+(\d+)", text)
    return int(m.group(1)) if m else 1
