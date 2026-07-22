import re
from typing import Optional

_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas",
    "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "district of columbia", "dc",
}

_US_STATE_ABBREVS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
}

_FOREIGN_SIGNALS = {
    # North America (non-US)
    "canada", "ontario", "british columbia", "alberta", "quebec",
    "toronto", "montreal", "vancouver bc",
    # UK / Ireland
    "united kingdom", "uk", "england", "scotland", "wales", "ireland",
    "london", "dublin",
    # Europe
    "germany", "france", "netherlands", "sweden", "denmark",
    "norway", "finland", "switzerland", "austria", "belgium",
    "spain", "italy", "portugal", "poland",
    "berlin", "amsterdam", "paris, france", "stockholm", "copenhagen",
    "oslo", "helsinki", "zurich", "brussels", "warsaw", "prague",
    "vienna", "budapest", "bucharest",
    # Israel
    "israel", "tel aviv",
    # APAC — East Asia
    "japan", "china", "taiwan", "south korea",
    "tokyo", "beijing", "shanghai", "seoul",
    # APAC — Southeast Asia
    "singapore", "vietnam", "indonesia", "philippines",
    "ho chi minh city", "hanoi", "surabaya", "cebu",
    # APAC — South Asia
    "india", "pakistan", "bangladesh", "sri lanka", "nepal",
    "hyderabad", "pune", "chennai", "kolkata", "ahmedabad",
    "jaipur", "surat", "lucknow", "kanpur", "nagpur",
    "noida", "gurgaon", "gurugram", "coimbatore", "kochi",
    "thiruvananthapuram", "bhubaneswar", "chandigarh", "indore", "patna",
    "karachi", "lahore", "dhaka", "colombo", "kathmandu",
    # APAC — Oceania
    "australia", "new zealand", "sydney", "melbourne",
    # LatAm
    "brazil", "mexico",
    # Middle East / Africa
    "emea", "apac", "latam", "amer", "asia pacific",
    "europe", "european union",
}

_REMOTE_SIGNALS = {"remote", "work from home", "wfh", "anywhere", "distributed", "us only", "usa only"}

# Pattern templates for check_description_geo.
# {sig} is replaced with the escaped foreign signal.
_DESC_GEO_PATTERNS = [
    r"based in\s+(?:our\s+)?(?:the\s+)?{sig}",
    r"located in\s+(?:our\s+)?(?:the\s+)?{sig}",
    r"must be located in\s+{sig}",
    r"working from\s+(?:our\s+)?(?:the\s+)?{sig}",
    r"this role is in\s+{sig}",
    r"position is based in\s+{sig}",
    r"our\s+{sig}\s+(?:office|team|headquarters|hq)",
]


def is_us_or_remote(location: str) -> bool:
    """Return True if location is in the US, remote, or empty (unknown)."""
    if not location or not location.strip():
        return True

    loc = location.strip().lower()

    # 1. Explicit remote / US signals → accept
    for signal in _REMOTE_SIGNALS:
        if signal in loc:
            return True

    # 2. Non-US terms → reject (checked BEFORE state abbreviations)
    for signal in _FOREIGN_SIGNALS:
        if signal in loc:
            # "vancouver, wa" contains "wa" but not "vancouver bc"
            if signal == "vancouver bc" and "vancouver, wa" in loc:
                return True
            return False

    # 3. "City, ST" pattern — check state abbreviation after comma
    m = re.search(r",\s*([a-z]{2})(?:\s|$|,)", loc)
    if m:
        abbrev = m.group(1)
        if abbrev in _US_STATE_ABBREVS:
            return True
        _CA_PROVINCES = {"bc", "on", "ab", "qc", "mb", "sk", "ns", "nb", "nl", "pe"}
        if abbrev in _CA_PROVINCES:
            return False

    for state in _US_STATES:
        if state in loc:
            return True

    # United States explicit mention
    if "united states" in loc or ", us" in loc or "(us)" in loc:
        return True

    # 4. Default — bare city with no signal, assume US/remote
    return True


def check_description_geo(description: str) -> bool:
    """Return True if the description contains a phrase indicating a non-US location."""
    if not description:
        return False

    lower = description.lower()

    for signal in _FOREIGN_SIGNALS:
        sig = re.escape(signal)
        for tmpl in _DESC_GEO_PATTERNS:
            if re.search(tmpl.format(sig=sig), lower):
                return True

    return False


def location_from_greenhouse(job: dict) -> str:
    """Extract location string from a Greenhouse API job dict."""
    office = job.get("location", {})
    if isinstance(office, dict):
        name = office.get("name", "") or ""
        if name:
            return name
    elif isinstance(office, str) and office:
        return office
    offices = job.get("offices", [])
    if offices and isinstance(offices, list):
        names = [o.get("name", "") for o in offices if o.get("name")]
        if names:
            return ", ".join(names)
    return ""


def location_from_lever(job: dict) -> str:
    """Extract location string from a Lever API job dict."""
    categories = job.get("categories", {})
    if isinstance(categories, dict):
        loc = categories.get("location", "")
        if loc:
            return loc
    loc = job.get("workplaceType", "")
    if loc.lower() == "remote":
        return "Remote"
    return ""


_TITLE_GEO_CODES = {
    # Multi-region acronyms
    "emea", "apac", "latam", "anz", "dach", "uki", "mena", "cee",
    # ISO-3166-1 alpha-3 country codes seen in B2B SaaS job titles
    "aut", "aus", "can", "gbr", "deu", "ind", "fra", "jpn",
    "sgp", "bra", "mex", "irl", "nld", "che",
}

_TITLE_GEO_WORDS = {
    # regions
    "europe", "asia pacific", "asia-pacific", "middle east", "africa",
    "nordics", "nordic",
    # countries
    "japan", "germany", "france", "italy", "spain", "netherlands",
    "australia", "india", "singapore", "canada", "ireland", "israel",
    "brazil", "mexico", "sweden", "norway", "denmark", "finland",
    "switzerland", "belgium", "poland", "portugal", "austria",
    "czech republic", "hungary", "romania", "turkey", "south korea",
    "china", "taiwan", "new zealand",
    # cities
    "london", "paris", "berlin", "tokyo", "sydney", "amsterdam",
    "dublin", "tel aviv", "stockholm", "copenhagen", "oslo", "helsinki",
    "zurich", "brussels", "warsaw", "prague", "vienna", "budapest",
    "bucharest", "toronto", "vancouver", "montreal",
}

# "UK" is two letters — match only when surrounded by non-alpha (word boundary)
_TITLE_GEO_ABBREVS_STRICT = {"uk", "namer"}


def is_title_geo_excluded(title: str) -> bool:
    """Return True if the job title contains an explicit non-US geographic restriction."""
    lower = title.lower()

    for code in _TITLE_GEO_CODES:
        if re.search(rf"\b{re.escape(code)}\b", lower):
            return True

    for abbrev in _TITLE_GEO_ABBREVS_STRICT:
        if re.search(rf"\b{re.escape(abbrev)}\b", lower):
            return True

    for phrase in _TITLE_GEO_WORDS:
        if phrase in lower:
            return True

    return False


def location_from_ashby(job: dict) -> str:
    """Extract location string from an Ashby API job dict."""
    loc = job.get("locationName", "") or job.get("location", "")
    if isinstance(loc, str):
        return loc
    if isinstance(loc, dict):
        return loc.get("name", "") or ""
    return ""
