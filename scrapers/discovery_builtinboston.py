"""Discovery scraper for Built In Boston (keyword rotation).

Flow per run:
  1. Load rotation cursor from ~/.job_sweep_bib_cursor.json (default 0)
  2. GET keyword search listing page for rotation_queue[cursor]
  3. Filter cards (skip Easy Apply, skip blocklisted companies, skip salary ceiling < $80K)
  4. For each survivor, check detail-request budget before each HTTP request
     (including retries); GET detail page; extract howToApply via jobPostInit
  5. Cards cut off by budget cap are written to Notion as Priority: Monitor
  6. Advance cursor by one slot (wraps at queue end) and persist it
  7. Run ATS detection → return DiscoveryListing (with seniority_text)
"""
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag
from curl_cffi import requests

from config import COMPANY_BLOCKLIST
from models import DiscoveryListing
from scrapers.ats_detector import extract_ats_domain, resolve_ats

_BASE_URL = "https://www.builtinboston.com"
_SEARCH_URL = _BASE_URL + "/jobs?search={keyword}&remote=true"
_IMPERSONATE = "chrome120"
_REQUEST_DELAY = 2.0
_RETRY_DELAYS = (5, 10, 20)
_SALARY_FLOOR_THRESHOLD = 80_000
_DETAIL_BUDGET = 20
_CURSOR_FILE = Path.home() / ".job_sweep_bib_cursor.json"
_ERROR_LOG = Path.home() / ".job_sweep_bib_errors.jsonl"


class _RateLimitError(Exception):
    pass


class _BudgetExceeded(Exception):
    pass


class _Budget:
    """Tracks total detail-page HTTP requests (including retries) per run."""

    def __init__(self, cap: int = _DETAIL_BUDGET):
        self.cap = cap
        self.count = 0

    def request(self) -> None:
        """Claim one request slot. Raises _BudgetExceeded if cap is already hit."""
        if self.count >= self.cap:
            raise _BudgetExceeded()
        self.count += 1


@dataclass
class BIBCard:
    title: str
    company_name: str
    detail_url: str
    job_id: int
    is_easy_apply: bool
    seniority_text: Optional[str]
    salary_text: Optional[str]


def _load_cursor() -> int:
    try:
        return int(json.loads(_CURSOR_FILE.read_text())["cursor"])
    except Exception:
        return 0


def _save_cursor(index: int) -> None:
    _CURSOR_FILE.write_text(json.dumps({"cursor": index}))


def run_rotation(
    rotation_queue: list[str],
    seen_detail_urls: set[str] | None = None,
    dry_run: bool = False,
) -> tuple[list[DiscoveryListing], int, int]:
    """
    Run one BIB rotation step: fetch the current keyword slot, process survivors
    within budget, write budget-capped cards to Notion monitor, advance cursor.

    Returns (results, unknown_ats, blocked).
    """
    cursor = _load_cursor()
    keyword = rotation_queue[cursor % len(rotation_queue)]
    next_cursor = (cursor + 1) % len(rotation_queue)
    budget = _Budget()

    url = _SEARCH_URL.format(keyword=quote(keyword))
    try:
        resp = requests.get(url, impersonate=_IMPERSONATE, timeout=20)
    except Exception as e:
        print(f"ERROR [BuiltInBoston] GET {url}: {e}")
        _save_cursor(next_cursor)
        return [], 0, 0

    if resp.status_code == 403:
        print(f"ERROR [BuiltInBoston] listing page blocked (403): {url}")
        _save_cursor(next_cursor)
        return [], 0, 1

    try:
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [BuiltInBoston] GET {url}: {e}")
        _save_cursor(next_cursor)
        return [], 0, 0

    cards = _parse_listing_page(resp.text)
    candidates = _filter_cards(cards)

    results: list[DiscoveryListing] = []
    unknown_ats = 0

    for i, card in enumerate(candidates):
        if seen_detail_urls is not None and card.detail_url in seen_detail_urls:
            continue

        try:
            apply_url = _fetch_apply_url(card.detail_url, budget)
            if seen_detail_urls is not None:
                seen_detail_urls.add(card.detail_url)
            time.sleep(_REQUEST_DELAY)
        except _BudgetExceeded:
            unseen = [
                c for c in candidates[i:]
                if seen_detail_urls is None or c.detail_url not in seen_detail_urls
            ]
            print(
                f"BUDGET CAP [BuiltInBoston] '{keyword}' — "
                f"writing {len(unseen)} unseen card(s) to monitor"
            )
            for mc in unseen:
                try:
                    _write_monitor_card(mc, dry_run)
                except Exception as e:
                    print(f"ERROR [BuiltInBoston] monitor card {mc.company_name}/{mc.title}: {e}")
            break
        except _RateLimitError:
            print(f"RATE LIMITED [BuiltInBoston] {card.detail_url} — skipping after 3 retries")
            continue
        except Exception as e:
            print(f"ERROR [BuiltInBoston] detail {card.detail_url}: {e}")
            continue

        if not apply_url:
            continue

        detected = resolve_ats(apply_url)
        if detected is None:
            domain = extract_ats_domain(apply_url)
            print(f"UNKNOWN ATS [BuiltInBoston] {card.company_name} | {card.title} | {domain}")
            unknown_ats += 1
            continue

        ats, slug = detected
        results.append(DiscoveryListing(
            title=card.title,
            url=apply_url,
            company_name=card.company_name,
            ats=ats,
            slug=slug,
            seniority_text=card.seniority_text,
        ))

    _save_cursor(next_cursor)
    return results, unknown_ats, 0


def _write_monitor_card(card: BIBCard, dry_run: bool) -> None:
    import notion_api as _notion_api  # lazy: keeps module importable without NOTION_API_KEY
    try:
        _notion_api.write_bib_monitor_card(
            title=card.title,
            company_name=card.company_name,
            detail_url=card.detail_url,
            salary_text=card.salary_text,
            seniority_text=card.seniority_text,
            dry_run=dry_run,
        )
    except Exception as e:
        import datetime as _dt
        import json as _j
        entry = {
            "time": _dt.datetime.now().isoformat(),
            "company": card.company_name,
            "title": card.title,
            "url": card.detail_url,
            "error": str(e),
        }
        try:
            with _ERROR_LOG.open("a") as fh:
                fh.write(_j.dumps(entry) + "\n")
        except Exception:
            pass
        raise


def _filter_cards(cards: list[BIBCard]) -> list[BIBCard]:
    """
    Return only BIBCards worth a detail-page fetch.

    Filtered out:
      - Easy Apply cards: apply happens on BIB itself — no external ATS URL exists.
      - Blocklisted companies: known aggregators or firms whose roles are never relevant.
      - Cards where salary ceiling < $80K: even the top of the posted range falls
        short of our minimum. salary_text=None passes through (treat as unknown).
        Wide ranges like "59K-172K" survive — the ceiling clears the threshold.
    Seniority is never a filter criterion — it passes through as metadata.
    """
    result = []
    for card in cards:
        if card.is_easy_apply:
            continue
        if card.company_name in COMPANY_BLOCKLIST:
            continue
        if card.salary_text is not None:
            ceiling = _parse_salary_ceiling(card.salary_text)
            if ceiling is not None and ceiling < _SALARY_FLOOR_THRESHOLD:
                continue
        result.append(card)
    return result


def _parse_salary_ceiling(salary_text: str) -> Optional[int]:
    """
    Extract the ceiling (maximum/second value) from salary strings like '72K-90K Annually'.
    For a single-number string like '95K', treats that number as both floor and ceiling.
    Returns an integer in dollars (e.g. 90000), or None if unparseable.
    """
    # Range with K suffix: NNK-NNK → second group is ceiling
    m = re.search(r'\d+(?:\.\d+)?\s*[Kk]\s*[-–]\s*(\d+(?:\.\d+)?)\s*[Kk]', salary_text)
    if m:
        return int(float(m.group(1)) * 1000)
    # Single K number (no range): treat as ceiling
    m = re.search(r'(\d+(?:\.\d+)?)\s*[Kk]', salary_text)
    if m:
        return int(float(m.group(1)) * 1000)
    # Non-K range: NNN,NNN-NNN,NNN → second group is ceiling
    m = re.search(r'\d[\d,]+\s*[-–]\s*(\d[\d,]+)', salary_text)
    if m:
        return int(m.group(1).replace(",", ""))
    # Single plain number
    m = re.search(r'(\d[\d,]+)', salary_text)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _parse_listing_page(html: str) -> list[BIBCard]:
    """
    Parse all job cards from a BIB listing page HTML string.
    Returns one BIBCard per card; skips cards with no href or numeric job ID.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[BIBCard] = []

    for card in soup.find_all(attrs={"data-id": "job-card"}):
        title_el = card.find(attrs={"data-id": "job-card-title"})
        if title_el is None:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href") if title_el.name == "a" else None
        if not href:
            a = title_el.find("a", href=True)
            href = a["href"] if a else None
        if not href:
            continue

        m = re.search(r"/(\d+)$", href)
        if not m:
            continue
        job_id = int(m.group(1))

        company_el = card.find(attrs={"data-id": "company-title"})
        company_name = company_el.get_text(strip=True) if company_el else ""

        results.append(BIBCard(
            title=title,
            company_name=company_name,
            detail_url=f"{_BASE_URL}{href}",
            job_id=job_id,
            is_easy_apply=bool(card.find("div", class_="easy-apply-box")),
            seniority_text=_get_icon_sibling_text(card, "fa-trophy"),
            salary_text=_get_icon_sibling_text(card, "fa-sack-dollar"),
        ))

    return results


def _get_icon_sibling_text(card: Tag, icon_class: str) -> Optional[str]:
    """
    Find an FA icon by class within a card, return text of its sibling <span>.

    BIB row structure:
        <div class="d-flex ...">           ← row container
          <div class="...">
            <i class="fa-regular {icon_class} ..."/>
          </div>
          <span class="font-barlow ...">VALUE</span>
        </div>
    """
    icon = card.find("i", class_=lambda c: c and icon_class in c.split())
    if icon is None:
        return None
    row = icon.parent.parent if icon.parent else None
    if row is None:
        return None
    span = row.find("span", recursive=False)
    if span is None:
        return None
    text = span.get_text(strip=True)
    return text if text else None


def _fetch_apply_url(detail_url: str, budget: _Budget) -> str:
    """Fetch a BIB job detail page and extract the howToApply URL from jobPostInit.

    Calls budget.request() before every HTTP attempt (initial + retries).
    Raises _BudgetExceeded immediately if the cap is hit before any attempt.
    Raises _RateLimitError if all retries are exhausted on 429.
    """
    budget.request()
    resp = requests.get(detail_url, impersonate=_IMPERSONATE, timeout=20)
    if resp.status_code == 429:
        for attempt, wait in enumerate(_RETRY_DELAYS, start=1):
            print(f"RATE LIMITED [BuiltInBoston] {detail_url} — retry {attempt}/3 in {wait}s")
            time.sleep(wait)
            budget.request()
            resp = requests.get(detail_url, impersonate=_IMPERSONATE, timeout=20)
            if resp.status_code != 429:
                break
        else:
            raise _RateLimitError(detail_url)
    resp.raise_for_status()
    return _extract_how_to_apply(resp.text)


def _extract_how_to_apply(html: str) -> str:
    """Parse howToApply URL from the Builtin.jobPostInit({...}) script block."""
    m = re.search(r"Builtin\.jobPostInit\((\{.*?\})\)", html, re.DOTALL)
    if not m:
        return ""
    try:
        data = json.loads(m.group(1))
        return data.get("job", {}).get("howToApply", "")
    except (json.JSONDecodeError, AttributeError):
        return ""
