from dataclasses import dataclass, field

import requests

import notion_api as notion

EXPIRY_MISS_THRESHOLD = 10

STAGES_TO_CHECK = {"Qualification", "Prioritized", "Create Resume", "Contacted / Applied"}

_CLOSED_PHRASES = ["no longer available", "position has been filled", "job not found"]


@dataclass
class ExpiryStats:
    still_live: int = 0
    newly_missed: int = 0
    auto_closed: int = 0
    errors: int = 0
    closed_roles: list[str] = field(default_factory=list)


def check_url_live(url: str, ats: str) -> bool:
    """Return True if the job URL is still live. Raises ValueError for unknown/empty URL."""
    if not url:
        raise ValueError("empty URL")

    ats_key = ats.lower()

    if ats_key in ("greenhouse", "lever"):
        resp = requests.get(url, timeout=15, allow_redirects=True)
        return resp.status_code == 200

    if ats_key == "ashby":
        resp = requests.get(url, timeout=15, allow_redirects=True)
        if resp.status_code == 404:
            return False
        body = resp.text.lower()
        return not any(phrase in body for phrase in _CLOSED_PHRASES)

    raise ValueError(f"Unknown ATS: {ats!r}")


def _infer_ats(url: str) -> str:
    """Infer ATS type from URL."""
    if "greenhouse.io" in url:
        return "Greenhouse"
    if "lever.co" in url:
        return "Lever"
    if "ashbyhq.com" in url:
        return "Ashby"
    return ""


def _apply_miss(consecutive_misses: int) -> tuple[int, bool]:
    """Return (new_count, should_close) after one miss."""
    new_count = consecutive_misses + 1
    return new_count, new_count >= EXPIRY_MISS_THRESHOLD


def run_expiry_check(dry_run: bool = False) -> ExpiryStats:
    stats = ExpiryStats()
    opps = notion.fetch_active_opportunities()

    for opp in opps:
        url = opp.get("url", "")
        name = opp.get("name", "")
        page_id = opp["page_id"]
        consecutive_misses = opp.get("consecutive_misses", 0)

        if not url:
            continue

        ats = _infer_ats(url)
        if not ats:
            continue

        try:
            live = check_url_live(url, ats)
        except Exception:
            stats.errors += 1
            continue

        if live:
            stats.still_live += 1
            if consecutive_misses > 0:
                notion.update_opportunity_expiry(page_id, consecutive_misses=0, dry_run=dry_run)
        else:
            new_count, should_close = _apply_miss(consecutive_misses)
            stats.newly_missed += 1
            if should_close:
                stats.auto_closed += 1
                stats.closed_roles.append(name)
                notion.update_opportunity_expiry(
                    page_id, consecutive_misses=new_count, stage="Closed Lost", dry_run=dry_run
                )
                print(f"AUTO-CLOSE {name} — {new_count} consecutive misses")
            else:
                notion.update_opportunity_expiry(page_id, consecutive_misses=new_count, dry_run=dry_run)

    return stats
