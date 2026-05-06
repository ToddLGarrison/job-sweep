import requests

from models import JobListing


def fetch_jobs(slug: str) -> list[JobListing]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [
        JobListing(title=job["text"], url=job["hostedUrl"])
        for job in data
        if job.get("text") and job.get("hostedUrl")
    ]
