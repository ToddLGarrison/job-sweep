from typing import Optional

from config import ROLE_TYPE_MAP, TARGET_TITLES, TITLE_EXCLUDE


def match_title(listing_title: str) -> Optional[str]:
    lower = listing_title.lower()
    if any(exc.lower() in lower for exc in TITLE_EXCLUDE):
        return None
    for target in TARGET_TITLES:
        if target.lower() in lower:
            return target
    return None


def get_role_type(matched_title: str) -> str:
    return ROLE_TYPE_MAP.get(matched_title, "Other")
