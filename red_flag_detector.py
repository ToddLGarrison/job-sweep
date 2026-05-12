import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RedFlag:
    code: str
    message: str


_TRAVEL_HEAVY_PATTERNS = [
    r"\b(50|60|70|75|80|90|100)\s*%\s*(travel|traveling|travelling)",
    r"\bheavy\s+travel\b",
    r"\bextensive\s+travel\b",
    r"\bfrequent\s+travel\b",
    r"\bsignificant\s+travel\b",
    r"\bup to (50|60|70|75|80|90|100)\s*%\s*travel",
    r"\brequires?\s+(significant|extensive|heavy|frequent)\s+travel",
    r"\btravel\s+(50|60|70|75|80|90|100)\s*%",
]

_QUOTA_PATTERNS = [
    r"\bquota[\s-]carrying\b",
    r"\bcarry\s+a\s+quota\b",
    r"\bcarrying\s+(a\s+)?quota\b",
    r"\bsales\s+quota\b",
    r"\brevenue\s+quota\b",
    r"\buncapped\s+commission\b",
    r"\bbase\s+\+\s+commission\b",
    r"\bbase\s+plus\s+commission\b",
]

_OUTBOUND_PATTERNS = [
    r"\bcold[\s-]call(s|ing)?\b",
    r"\boutbound\s+(sales|calls?|prospecting)\b",
    r"\bprospecting\b",
    r"\blead\s+generation\b",
    r"\bpipeline\s+generation\b",
    r"\bhunter\s+mentality\b",
    r"\bnew\s+logo\b",
    r"\bSDR\b",
    r"\bBDR\b",
    r"\bbusiness\s+development\s+rep",
]

_SUPPORT_ONLY_PATTERNS = [
    r"\btier[\s-]?1\s+(support|agent)\b",
    r"\bhelp[\s-]?desk\b",
    r"\bticket[\s-]based\b",
    r"\bticket\s+queue\b",
    r"\bL1\s+support\b",
    r"\blevel[\s-]?1\s+support\b",
    r"\bcall\s+center\b",
    r"\bcallcenter\b",
    r"\binbound\s+(support\s+)?calls?\b",
    r"\bsupport\s+queue\b",
]

_HARDWARE_ONLY_PATTERNS = [
    r"\bphysical\s+installation\b",
    r"\bon[\s-]?site\s+(installation|deployment|setup)\b",
    r"\bhardware\s+(installation|deployment|setup|repair|maintenance)\b",
    r"\bracking?\s+and\s+(stacking|cabling)\b",
    r"\bdata\s+center\s+(operations?|technician)\b",
    r"\bfield\s+technician\b",
    r"\bbreak[\s/-]fix\b",
]

_LEADERSHIP_REQ_PATTERNS = [
    r"\bmanage\s+a\s+team\b",
    r"\bleading\s+a\s+team\b",
    r"\bteam\s+lead(er)?\s+required\b",
    r"\bpeople\s+manager\b",
    r"\bdirect\s+reports?\b",
    r"\bmanagement\s+experience\s+required\b",
    r"\b\d+\+?\s+years?\s+(of\s+)?management\b",
    r"\bprevious\s+management\s+experience\b",
    r"\bprior\s+management\s+experience\b",
    r"\bexperience\s+managing\s+(a\s+)?team\b",
]


def _matches_any(text: str, patterns: list[str]) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def check_red_flags(title: str, description: str) -> list[RedFlag]:
    """Scan title + description for red flags. Returns list of RedFlag objects."""
    combined = f"{title}\n{description}"

    flags: list[RedFlag] = []

    hit = _matches_any(combined, _TRAVEL_HEAVY_PATTERNS)
    if hit:
        flags.append(RedFlag(code="TRAVEL_HEAVY", message=f"Heavy travel detected: '{hit}'"))

    hit = _matches_any(combined, _QUOTA_PATTERNS)
    if hit:
        flags.append(RedFlag(code="QUOTA_CARRYING", message=f"Quota/commission role detected: '{hit}'"))

    hit = _matches_any(combined, _OUTBOUND_PATTERNS)
    if hit:
        flags.append(RedFlag(code="OUTBOUND_SALES", message=f"Outbound sales focus detected: '{hit}'"))

    hit = _matches_any(combined, _SUPPORT_ONLY_PATTERNS)
    if hit:
        flags.append(RedFlag(code="SUPPORT_ONLY", message=f"Tier-1 support role detected: '{hit}'"))

    hit = _matches_any(combined, _HARDWARE_ONLY_PATTERNS)
    if hit:
        flags.append(RedFlag(code="HARDWARE_ONLY", message=f"Hardware-only role detected: '{hit}'"))

    hit = _matches_any(combined, _LEADERSHIP_REQ_PATTERNS)
    if hit:
        flags.append(RedFlag(code="LEADERSHIP_REQ", message=f"Management experience required: '{hit}'"))

    return flags
