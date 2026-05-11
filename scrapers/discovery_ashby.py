import re

import requests

from models import DiscoveryListing


def fetch_all_jobs(company: dict) -> list[DiscoveryListing]:
    slug = company["slug"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for job in data.get("jobPostings", []):
        title = job.get("title", "")
        apply_url = job.get("jobUrl", "")
        if not title or not apply_url:
            continue
        description = (
            job.get("descriptionPlain")
            or _strip_html(job.get("descriptionHtml", ""))
            or _strip_html(job.get("description", ""))
        )
        results.append(DiscoveryListing(
            title=title,
            url=apply_url,
            company_name=company["name"],
            ats="Ashby",
            slug=slug,
            description=description,
        ))
    return results


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)
