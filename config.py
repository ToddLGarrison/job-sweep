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
    "SmartRecruiters": "scrapers.smartrecruiters",
    "Comeet": "scrapers.comeet",
    "Workday": "scrapers.workday",
}

# --- Discovery ---

DISCOVERY_ENABLED = True
SECONDARY_JD_SCAN_ENABLED = True

DISCOVERY_TITLES = [
    "Solutions Engineer",
    "Solutions Consultant",
    "Solutions Architect",
    "Customer Success Engineer",
    "Technical Account Manager",
    "Implementation Engineer",
    "Implementation Consultant",
    "Onboarding Engineer",
    "Technical Support Engineer",
    "Professional Services Engineer",
    "Professional Services Consultant",
    "Professional Services Manager",
    "Post-Sales Engineer",
    "Pre-Sales Engineer",
    "Customer Engineer",
    "Partner Engineer",
    "Technical Consultant",
    "Revenue Engineer",
    "Client Engineer",
    "Field Engineer",
    "Integration Specialist",
    "Solutions Specialist",
    "Engagement Manager",
    "Technical Onboarding Manager",
    "Customer Solutions Engineer",
    "Enterprise Customer Engineer",
    "Client Solutions Engineer",
    "Sales Engineer",
    "Forward Deployed Engineer",
]

DISCOVERY_JD_KEYWORDS = [
    "post-sales",
    "implementation",
    "onboarding",
    "hardware deployment",
    "customer-facing technical",
    "LMS integration",
    "solutions engineering",
    "technical account",
    "customer success engineer",
    "professional services",
    "integration engineer",
    "technical onboarding",
]

DISCOVERY_ROLE_TYPE_MAP = {
    "Solutions Engineer": "Solutions Engineer",
    "Solutions Consultant": "Solutions Engineer",
    "Solutions Architect": "Solutions Engineer",
    "Customer Success Engineer": "Customer Success",
    "Technical Account Manager": "Customer Success",
    "Implementation Engineer": "Implementation",
    "Implementation Consultant": "Implementation",
    "Onboarding Engineer": "Implementation",
    "Technical Support Engineer": "Customer Success",
    "Professional Services Engineer": "Implementation",
    "Professional Services Consultant": "Implementation",
    "Professional Services Manager": "Implementation",
    "Post-Sales Engineer": "Customer Success",
    "Pre-Sales Engineer": "Solutions Engineer",
    "Customer Engineer": "Customer Success",
    "Partner Engineer": "Solutions Engineer",
    "Technical Consultant": "Solutions Engineer",
    "Revenue Engineer": "Solutions Engineer",
    "Client Engineer": "Customer Success",
    "Field Engineer": "Solutions Engineer",
    "Integration Specialist": "Implementation",
    "Solutions Specialist": "Solutions Engineer",
    "Engagement Manager": "Implementation",
    "Technical Onboarding Manager": "Implementation",
    "Customer Solutions Engineer": "Customer Success",
    "Enterprise Customer Engineer": "Customer Success",
    "Client Solutions Engineer": "Customer Success",
    "Sales Engineer": "Solutions Engineer",
    "Forward Deployed Engineer": "Solutions Engineer",
}

BUILTINBOSTON_ENABLED = True
VENTUREFIZZ_ENABLED = True

# Lever and Ashby companies not yet in the Notion Companies DB.
# Format: {"name": "Company Name", "ats": "Lever" | "Ashby", "slug": "companyslug"}
DISCOVERY_SEED_COMPANIES: list[dict] = []
