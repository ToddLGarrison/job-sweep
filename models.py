from dataclasses import dataclass
from typing import Optional


@dataclass
class Company:
    page_id: str
    name: str
    ats: str
    ats_slug: str
    tier: Optional[str] = None


@dataclass
class JobListing:
    title: str
    url: str


@dataclass
class Opportunity:
    company: Company
    listing: JobListing
    matched_title: str
    role_type: str
    verified: str  # "__YES__" or "__NO__"
    ats: str
    notes: Optional[str] = None
