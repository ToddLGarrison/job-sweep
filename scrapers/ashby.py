import requests

from models import JobListing


def fetch_jobs(slug: str) -> list[JobListing]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [
        JobListing(title=job["title"], url=job["jobUrl"])
        for job in data.get("jobPostings", [])
        if job.get("title") and job.get("jobUrl")
    ]
