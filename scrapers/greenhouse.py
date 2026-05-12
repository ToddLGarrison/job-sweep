import re

import requests

from geo_filter import is_us_or_remote, location_from_greenhouse
from models import JobListing


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    geo_filtered = 0
    for job in data.get("jobs", []):
        title = job.get("title", "")
        apply_url = job.get("absolute_url", "")
        if not title or not apply_url:
            continue
        location = location_from_greenhouse(job)
        if not is_us_or_remote(location):
            geo_filtered += 1
            continue
        description = _strip_html(job.get("content", ""))
        results.append(JobListing(title=title, url=apply_url, location=location, description=description))
    return results, geo_filtered


def _strip_html(text: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", text))
