import re

import requests

from models import DiscoveryListing


def fetch_all_jobs(company: dict) -> list[DiscoveryListing]:
    slug = company["slug"]
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for job in data:
        title = job.get("text", "")
        apply_url = job.get("hostedUrl", "")
        if not title or not apply_url:
            continue
        results.append(DiscoveryListing(
            title=title,
            url=apply_url,
            company_name=company["name"],
            ats="Lever",
            slug=slug,
            description=_build_description(job),
        ))
    return results


def _build_description(job: dict) -> str:
    parts = []
    plain = job.get("descriptionPlain") or _strip_html(job.get("description", ""))
    if plain:
        parts.append(plain)
    for section in job.get("lists", []):
        content = section.get("content", "")
        if content:
            parts.append(_strip_html(content))
    additional = job.get("additionalPlain") or _strip_html(job.get("additional", ""))
    if additional:
        parts.append(additional)
    return " ".join(parts)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)
