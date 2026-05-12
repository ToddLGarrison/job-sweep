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
    "canada", "ontario", "british columbia", "alberta", "quebec",
    "united kingdom", "uk", "england", "scotland", "wales",
    "germany", "france", "netherlands", "sweden", "denmark",
    "norway", "finland", "switzerland", "austria", "belgium",
    "spain", "italy", "portugal", "ireland", "poland",
    "australia", "new zealand", "singapore", "japan", "india",
    "israel", "brazil", "mexico",
    "emea", "apac", "latam", "amer", "asia pacific",
    "europe", "european union",
    "london", "toronto", "montreal", "vancouver bc", "sydney",
    "melbourne", "berlin", "amsterdam", "paris, france",
    "tel aviv",
}

_REMOTE_SIGNALS = {"remote", "work from home", "wfh", "anywhere", "distributed", "us only", "usa only"}


def is_us_or_remote(location: str) -> bool:
    """Return True if location is in the US, remote, or empty (unknown)."""
    if not location or not location.strip():
        return True

    loc = location.strip().lower()

    for signal in _REMOTE_SIGNALS:
        if signal in loc:
            return True

    for signal in _FOREIGN_SIGNALS:
        if signal in loc:
            # "vancouver, wa" contains "wa" but not "vancouver bc"
            if signal == "vancouver bc" and "vancouver, wa" in loc:
                return True
            return False

    # "City, ST" pattern — check state abbreviation after comma
    m = re.search(r",\s*([a-z]{2})(?:\s|$|,)", loc)
    if m:
        abbrev = m.group(1)
        if abbrev in _US_STATE_ABBREVS:
            return True
        # Two-letter non-US codes (bc, on, ab for Canada provinces)
        _CA_PROVINCES = {"bc", "on", "ab", "qc", "mb", "sk", "ns", "nb", "nl", "pe"}
        if abbrev in _CA_PROVINCES:
            return False

    for state in _US_STATES:
        if state in loc:
            return True

    # United States explicit mention
    if "united states" in loc or ", us" in loc or "(us)" in loc:
        return True

    # Bare city names with no country/state signal — assume US/remote
    return True


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
    "emea", "apac", "latam", "anz", "dach", "uki", "mena", "cee",
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
