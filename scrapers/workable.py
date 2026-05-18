import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

_API_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
_APPLY_URL = "https://apply.workable.com/{slug}/j/{shortcode}"
_BODY = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    results = []
    geo_filtered = 0
    token = None

    while True:
        body = dict(_BODY)
        if token:
            body["token"] = token
        try:
            resp = requests.post(
                _API_URL.format(slug=slug),
                json=body,
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"ERROR [Workable/{slug}]: {e}")
            return [], 0

        data = resp.json()
        postings = data.get("results", [])

        for posting in postings:
            title = posting.get("title", "")
            shortcode = posting.get("shortcode", "")
            if not title or not shortcode:
                continue

            if posting.get("state") != "published":
                continue

            location = _extract_location(posting)

            if not is_us_or_remote(location):
                geo_filtered += 1
                continue

            if is_title_geo_excluded(title):
                geo_filtered += 1
                continue

            apply_url = _APPLY_URL.format(slug=slug, shortcode=shortcode)
            results.append(JobListing(
                title=title,
                url=apply_url,
                location=location,
            ))

        token = data.get("nextPage")
        if not token or not postings:
            break

    return results, geo_filtered


def _extract_location(posting: dict) -> str:
    if posting.get("remote"):
        return "Remote"
    loc = posting.get("location", {})
    if not loc:
        return ""
    country_code = loc.get("countryCode", "")
    city = loc.get("city", "") or ""
    region = loc.get("region", "") or ""
    if country_code == "US":
        if city and region:
            return f"{city}, {region}"
        return city or region or "United States"
    country = loc.get("country", "") or ""
    if city and country:
        return f"{city}, {country}"
    return country or city
