import datetime
from typing import Optional

from notion_client import Client

from config import COMPANIES_DB_ID, NOTION_API_KEY, OPPORTUNITIES_DB_ID
from models import Company, Opportunity

_client = Client(auth=NOTION_API_KEY, timeout_ms=120_000)


def fetch_companies() -> list[Company]:
    companies = []
    cursor = None
    while True:
        kwargs: dict = {}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _client.data_sources.query(COMPANIES_DB_ID, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            name = _get_title(props.get("Name", {}))
            ats = _get_select(props.get("ATS", {}))
            ats_slug = _get_text(props.get("ATS Slug", {}))
            tier = _get_select(props.get("Tier", {}))
            if not ats or not ats_slug:
                print(f"WARNING: Skipping '{name}' — missing ATS or ATS Slug")
                continue
            companies.append(Company(
                page_id=page["id"],
                name=name,
                ats=ats,
                ats_slug=ats_slug,
                tier=tier,
            ))
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return companies


def find_company_by_name(name: str) -> Optional[Company]:
    resp = _client.data_sources.query(
        COMPANIES_DB_ID,
        filter={"property": "Name", "title": {"contains": name}},
    )
    for page in resp.get("results", []):
        props = page["properties"]
        found_name = _get_title(props.get("Name", {}))
        if found_name.lower() == name.lower():
            return Company(
                page_id=page["id"],
                name=found_name,
                ats=_get_select(props.get("ATS", {})),
                ats_slug=_get_text(props.get("ATS Slug", {})),
                tier=_get_select(props.get("Tier", {})),
            )
    return None


def create_company(
    name: str, ats: str, slug: str, dry_run: bool = False
) -> Company:
    today = datetime.date.today().isoformat()
    properties: dict = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Tier": {"select": {"name": "🥈 Tier 2 – Target"}},
        "Hiring": {"select": {"name": "Relevant"}},
        "ATS": {"select": {"name": ats}},
        "ATS Slug": {"rich_text": [{"text": {"content": slug}}]},
        "Last Swept": {"date": {"start": today}},
    }
    if dry_run:
        print(f"  [DRY RUN] Would create company: {name} [{ats}/{slug}]")
        return Company(page_id="dry-run", name=name, ats=ats, ats_slug=slug)
    resp = _client.pages.create(
        parent={"data_source_id": COMPANIES_DB_ID},
        properties=properties,
    )
    return Company(page_id=resp["id"], name=name, ats=ats, ats_slug=slug)


def query_by_url(url: str) -> bool:
    resp = _client.data_sources.query(
        OPPORTUNITIES_DB_ID,
        filter={"property": "Job URL", "url": {"equals": url}},
    )
    return len(resp["results"]) > 0


def query_by_name(company_name: str, role_title: str) -> bool:
    resp = _client.data_sources.query(
        OPPORTUNITIES_DB_ID,
        filter={
            "and": [
                {"property": "Name", "title": {"contains": company_name}},
                {"property": "Name", "title": {"contains": role_title}},
            ]
        },
    )
    return len(resp["results"]) > 0


def write_opportunity(opp: Opportunity, dry_run: bool = False) -> None:
    year = datetime.date.today().year
    name = f"{opp.company.name} / {opp.listing.title} / {year}"
    properties: dict = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Stage": {"select": {"name": "Qualification"}},
        "Source": {"select": {"name": opp.source}},
        "Job URL": {"url": opp.listing.url},
        "Verified": {"checkbox": opp.verified == "__YES__"},
        "Company": {"relation": [{"id": opp.company.page_id}]},
        "Role Type": {"select": {"name": opp.role_type}},
    }
    if opp.notes:
        properties["Notes"] = {"rich_text": [{"text": {"content": opp.notes}}]}
    if opp.description:
        properties["Description"] = {"rich_text": [{"text": {"content": opp.description}}]}
    if dry_run:
        print(f"  [DRY RUN] Would create: {name}")
        return
    _client.pages.create(
        parent={"data_source_id": OPPORTUNITIES_DB_ID},
        properties=properties,
    )


def fetch_active_opportunities() -> list[dict]:
    """Fetch opportunities in stages eligible for expiry checking."""
    stages = ["Qualification", "Prioritized", "Create Resume", "Contacted / Applied"]
    filter_clauses = [
        {"property": "Stage", "select": {"equals": s}} for s in stages
    ]
    opps = []
    cursor = None
    while True:
        kwargs: dict = {"filter": {"or": filter_clauses}}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _client.data_sources.query(OPPORTUNITIES_DB_ID, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            name = _get_title(props.get("Name", {}))
            url = props.get("Job URL", {}).get("url", "") or ""
            misses_prop = props.get("Consecutive Misses", {})
            consecutive_misses = int(misses_prop.get("number") or 0)
            opps.append({
                "page_id": page["id"],
                "name": name,
                "url": url,
                "consecutive_misses": consecutive_misses,
            })
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return opps


def fetch_pipeline_snapshot() -> dict[str, int]:
    """Return opportunity counts per active stage for the digest pipeline section."""
    stages = ["Qualification", "Prioritized", "Create Resume", "Contacted / Applied"]
    counts: dict[str, int] = {s: 0 for s in stages}
    filter_clauses = [{"property": "Stage", "select": {"equals": s}} for s in stages]
    cursor = None
    while True:
        kwargs: dict = {"filter": {"or": filter_clauses}}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = _client.data_sources.query(OPPORTUNITIES_DB_ID, **kwargs)
        for page in resp["results"]:
            stage = _get_select(page["properties"].get("Stage", {}))
            if stage in counts:
                counts[stage] += 1
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return counts


def update_opportunity_expiry(
    page_id: str,
    consecutive_misses: int,
    stage: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    properties: dict = {"Consecutive Misses": {"number": consecutive_misses}}
    if stage:
        properties["Stage"] = {"select": {"name": stage}}
    if dry_run:
        action = f"close + misses={consecutive_misses}" if stage else f"misses={consecutive_misses}"
        print(f"  [DRY RUN] Would update expiry {page_id}: {action}")
        return
    _client.pages.update(page_id=page_id, properties=properties)


def update_company(page_id: str, hiring: Optional[str], dry_run: bool = False) -> None:
    today = datetime.date.today().isoformat()
    properties: dict = {"Last Swept": {"date": {"start": today}}}
    if hiring is not None:
        properties["Hiring"] = {"select": {"name": hiring}}
    if dry_run:
        return
    _client.pages.update(page_id=page_id, properties=properties)


def _get_title(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("title", []))


def _get_select(prop: dict) -> str:
    sel = prop.get("select")
    return sel["name"] if sel else ""


def _get_text(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
