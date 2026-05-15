"""Detect ATS vendor and slug from a job apply URL."""
import re
from urllib.parse import urlparse


def extract_ats_domain(url: str) -> str:
    """Return the hostname from a URL (e.g. 'jobs.jobvite.com'), or '' if unparseable."""
    if not url:
        return ""
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def detect_ats(url: str) -> tuple[str, str] | None:
    """Return (ats_name, slug) or None if the URL doesn't match a known ATS.

    Patterns:
      Greenhouse:      job-boards.greenhouse.io/{slug}/jobs/{id}
                       boards.greenhouse.io/{slug}/jobs/{id}
      Lever:           jobs.lever.co/{slug}/{uuid}
      Ashby:           jobs.ashbyhq.com/{slug}/{uuid}
      Workday:         {tenant}.wd{N}.myworkdayjobs.com/[en-XX/]{board}/job/...
      SmartRecruiters: jobs.smartrecruiters.com/{Slug}/...
      Comeet:          www.comeet.com/jobs/{slug}/{token}/...
    """
    if not url:
        return None

    # Greenhouse
    m = re.search(
        r"https?://(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)/jobs/\d+",
        url,
    )
    if m:
        return ("Greenhouse", m.group(1))

    # Lever
    m = re.search(
        r"https?://jobs\.lever\.co/([^/?#]+)/[0-9a-f]{8}-[0-9a-f-]{27}",
        url,
    )
    if m:
        return ("Lever", m.group(1))

    # Ashby
    m = re.search(
        r"https?://jobs\.ashbyhq\.com/([^/?#]+)/[0-9a-f]{8}-[0-9a-f-]{27}",
        url,
    )
    if m:
        return ("Ashby", m.group(1))

    # Workday: {tenant}.wd{N}.myworkdayjobs.com/[locale/]{board}/job/...
    m = re.search(
        r"https?://([a-z0-9][a-z0-9.-]*\.wd\d+)\.myworkdayjobs\.com"
        r"/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)/job/",
        url,
        re.IGNORECASE,
    )
    if m:
        return ("Workday", f"{m.group(1).lower()}/{m.group(2)}")

    # SmartRecruiters
    m = re.search(
        r"https?://jobs\.smartrecruiters\.com/([^/?#]+)/",
        url,
    )
    if m:
        return ("SmartRecruiters", m.group(1))

    # Comeet
    m = re.search(
        r"https?://www\.comeet\.com/jobs/([^/?#]+)/([^/?#]+)/",
        url,
    )
    if m:
        return ("Comeet", f"{m.group(1)}/{m.group(2)}")

    return None
