import re

import requests

from geo_filter import is_us_or_remote, location_from_ashby
from models import DiscoveryListing


def fetch_all_jobs(company: dict) -> tuple[list[DiscoveryListing], int]:
    slug = company["slug"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    geo_filtered = 0
    for job in data.get("jobPostings", []):
        title = job.get("title", "")
        apply_url = job.get("jobUrl", "")
        if not title or not apply_url:
            continue
        location = location_from_ashby(job)
        if not is_us_or_remote(location):
            geo_filtered += 1
            continue
        description = (
            job.get("descriptionPlain")
            or _strip_html(job.get("descriptionHtml", ""))
            or _strip_html(job.get("description", ""))
        )
        if description:
            description = description[:1500]
        results.append(DiscoveryListing(
            title=title,
            url=apply_url,
            company_name=company["name"],
            ats="Ashby",
            slug=slug,
            description=description,
            location=location,
        ))
    return results, geo_filtered


def _strip_html(text: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", text))
