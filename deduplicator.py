from urllib.parse import urlparse, urlunparse

import notion_api as notion
from models import Company, JobListing


def _normalize_url(url: str) -> str:
    """Strip query string and fragment, and remove trailing slash from path."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def is_duplicate(company: Company, listing: JobListing) -> bool:
    if listing.url:
        normalized = _normalize_url(listing.url)
        if notion.query_by_url(listing.url) or notion.query_by_url(normalized):
            return True
    if notion.query_by_name(company.name, listing.title):
        return True
    return False
