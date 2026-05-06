import os

from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.environ["NOTION_API_KEY"]

COMPANIES_DB_ID = "266cf0ba-f470-8286-9694-07cb7a7d7d72"
OPPORTUNITIES_DB_ID = "eebcf0ba-f470-83bd-8a01-07d8bc25988e"

TARGET_TITLES = [
    "Solutions Engineer",
    "Solutions Consultant",
    "Solutions Architect",
    "Customer Success Engineer",
    "Customer Success Manager",
    "Technical Account Manager",
    "Implementation Engineer",
]

ROLE_TYPE_MAP = {
    "Solutions Engineer": "Solutions Engineer",
    "Solutions Consultant": "Solutions Engineer",
    "Solutions Architect": "Solutions Engineer",
    "Customer Success Engineer": "Customer Success",
    "Customer Success Manager": "Customer Success",
    "Technical Account Manager": "Customer Success",
    "Implementation Engineer": "Implementation",
}

TITLE_EXCLUDE = [
    "Senior",
    "Lead",
    "Staff",
    "Principal",
    "Director",
    "VP",
    "Head of",
]

ATS_SCRAPER_MAP = {
    "Greenhouse": "scrapers.greenhouse",
    "Lever": "scrapers.lever",
    "Ashby": "scrapers.ashby",
}
