import re
from urllib.parse import quote

import requests

from models import DiscoveryListing


def search_jobs(keyword: str) -> list[DiscoveryListing]:
    url = (
        f"https://boards-api.greenhouse.io/v1/boards/greenhouse/jobs"
        f"?content=true&q={quote(keyword)}"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for job in data.get("jobs", []):
        title = job.get("title", "")
        apply_url = job.get("absolute_url", "")
        if not title or not apply_url:
            continue
        slug = _extract_slug(apply_url)
        results.append(DiscoveryListing(
            title=title,
            url=apply_url,
            company_name=_slug_to_name(slug),
            ats="Greenhouse",
            slug=slug,
            description=_strip_html(job.get("content", "")),
        ))
    return results


def _extract_slug(url: str) -> str:
    # https://job-boards.greenhouse.io/{slug}/jobs/{id}
    try:
        after_domain = url.split("greenhouse.io/")[1]
        return after_domain.split("/")[0]
    except (IndexError, AttributeError):
        return ""


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)
