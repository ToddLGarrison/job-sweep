import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

_LIST_URL = "https://{slug}.bamboohr.com/careers/list"
_JOB_URL = "https://{slug}.bamboohr.com/careers/{job_id}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://{slug}.bamboohr.com/careers",
}


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    url = _LIST_URL.format(slug=slug)
    headers = {**_HEADERS, "Referer": f"https://{slug}.bamboohr.com/careers"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [BambooHR/{slug}]: {e}")
        return [], 0

    try:
        data = resp.json()
    except Exception as e:
        print(f"ERROR [BambooHR/{slug}]: JSON parse error: {e}")
        return [], 0

    results = []
    geo_filtered = 0

    for job in data.get("result", []):
        title = (job.get("jobOpeningName") or "").strip()
        job_id = str(job.get("id") or "").strip()
        if not title or not job_id:
            continue

        location = _extract_location(job)

        if not is_us_or_remote(location):
            geo_filtered += 1
            continue

        if is_title_geo_excluded(title):
            geo_filtered += 1
            continue

        job_url = _JOB_URL.format(slug=slug, job_id=job_id)
        results.append(JobListing(title=title, url=job_url, location=location))

    return results, geo_filtered


def _extract_location(job: dict) -> str:
    if job.get("isRemote"):
        return "Remote"
    loc = job.get("location") or {}
    city = (loc.get("city") or "").strip()
    state = (loc.get("state") or "").strip()
    if city and state:
        return f"{city}, {state}"
    return city or state
