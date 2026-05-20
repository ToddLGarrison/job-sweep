"""Detect ATS vendor and slug from a job apply URL."""
import re
from urllib.parse import urlparse

import requests

# Cache keyed by original URL so each URL is resolved at most once per process run.
_resolve_cache: dict[str, tuple[str, str] | None] = {}


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
      YC:              workatastartup.com/* or account.ycombinator.com/*
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

    # YC Work at a Startup — apply URLs route through YC auth or directly to WaaS
    if re.search(r"https?://(?:www\.workatastartup\.com|account\.ycombinator\.com)/", url):
        # Try to extract company slug from workatastartup.com/companies/{slug}
        m = re.search(r"workatastartup\.com/companies/([^/?#]+)", url)
        slug = m.group(1) if m else ""
        return ("YC", slug)

    return None


def resolve_ats(url: str, follow_redirects: bool = True) -> tuple[str, str] | None:
    """Like detect_ats, but follows HTTP redirects to handle custom career page URLs.

    1. Tries detect_ats(url) first — returns immediately with no HTTP call on match.
    2. Makes a HEAD request; if HEAD fails, falls back to GET.
    3. Runs detect_ats on the final resolved URL.
    4. Caches results so each original URL is fetched at most once.
    """
    if not url:
        return None

    if url in _resolve_cache:
        return _resolve_cache[url]

    # Direct match — no HTTP needed.
    result = detect_ats(url)
    if result is not None:
        _resolve_cache[url] = result
        return result

    if not follow_redirects:
        _resolve_cache[url] = None
        return None

    final_url: str | None = None

    # HEAD first — lighter than GET.
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        final_url = resp.url
    except Exception:
        pass  # HEAD rejected or timed out — try GET below.

    # GET fallback when HEAD failed.
    if final_url is None:
        try:
            resp = requests.get(url, allow_redirects=True, timeout=10)
            final_url = resp.url
        except Exception:
            _resolve_cache[url] = None
            return None

    result = detect_ats(final_url)
    if result is not None and final_url != url:
        print(f"Resolved {url} → {final_url}")

    _resolve_cache[url] = result
    return result
