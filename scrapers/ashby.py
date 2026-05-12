import re

import requests

from geo_filter import is_us_or_remote, location_from_ashby
from models import JobListing


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
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
            or ""
        )
        results.append(JobListing(title=title, url=apply_url, location=location, description=description))
    return results, geo_filtered


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)
