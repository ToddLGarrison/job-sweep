import requests

from models import JobListing


def fetch_jobs(slug: str) -> list[JobListing]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [
        JobListing(title=job["title"], url=job["absolute_url"])
        for job in data.get("jobs", [])
        if job.get("title") and job.get("absolute_url")
    ]
