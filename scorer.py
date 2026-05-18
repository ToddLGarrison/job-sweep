import time

import anthropic
import requests
from bs4 import BeautifulSoup

import notion_api as notion
from config import ANTHROPIC_API_KEY

_VALID_SCORES = {"⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"}
_SCORE_MODEL = "claude-haiku-4-5-20251001"
_DESC_MAX_CHARS = 3000

_anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are evaluating job postings for Todd Garrison, a technical customer-facing
professional targeting Solutions Engineer, Customer Success Engineer, Technical
Account Manager, and Implementation Engineer roles at B2B SaaS companies.

Todd's profile:
- 7+ years customer-facing technical experience (SE, CSM, CSE)
- Strong: SSO/SAML/SCIM, REST APIs, Postman, hardware deployments,
  enterprise LMS integrations, JavaScript, Python, SQL, Retool
- Comfortable: pre-sales demos, technical scoping, onboarding, troubleshooting
- Gaps: Docker/Kubernetes, Java/.NET/Go as core requirement, 5+ years
  dedicated SE title experience, deep cloud infrastructure
- Prefers: remote or Boston/Portland ME hybrid, $80K-$120K+ base,
  B2B SaaS, no quota-carrying sales, no people management

Scoring rubric:
⭐⭐⭐⭐⭐ Excellent: Right role type, right seniority, remote/Boston/Portland,
  salary $80K+, no red flag requirements, strong profile match
⭐⭐⭐⭐ Strong: Good match but missing one factor (comp unlisted, slight
  seniority stretch, minor domain gap)
⭐⭐⭐ Good: Role type matches but 1-2 gaps (domain knowledge preferred,
  slightly more SE experience requested than Todd has)
⭐⭐ Weak: Significant gap, or role is more sales-heavy than preferred,
  or comp likely below target
⭐ Poor: Multiple gaps, wrong role type, or auto-exclude criteria present

Auto-exclude (always ⭐):
- Requires 5+ years dedicated SE title experience
- Core requirement: Java, .NET, or Go
- Must-have: Docker or Kubernetes
- Quota-carrying sales role
- Extensive travel required
- People management required
- Comp ceiling below $80K

Respond with ONLY the star rating on a single line. Nothing else.
Valid responses: ⭐, ⭐⭐, ⭐⭐⭐, ⭐⭐⭐⭐, ⭐⭐⭐⭐⭐"""

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def score_opportunity(title: str, description: str) -> str | None:
    """Call Claude API and return a star rating string, or None on failure."""
    user_content = f"Job Title: {title}\n\nJob Description:\n{description}"
    try:
        msg = _anthropic_client.messages.create(
            model=_SCORE_MODEL,
            max_tokens=10,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        score = msg.content[0].text.strip()
        if score not in _VALID_SCORES:
            print(f"ERROR [scorer] Unexpected response: {score!r}")
            return None
        return score
    except Exception as e:
        print(f"ERROR [scorer] API call failed: {e}")
        return None


def batch_score_unscored(dry_run: bool = False) -> dict:
    """Score all active opportunities with an empty Fit Score field.

    Returns {"scored": N, "skipped": N, "errors": N}.
    """
    opps = notion.fetch_unscored_opportunities()
    scored = skipped = errors = 0

    for opp in opps:
        name = opp.get("name", "")
        job_url = opp.get("job_url", "")
        page_id = opp["page_id"]

        # Defensive guard: skip if somehow already scored
        if opp.get("fit_score"):
            skipped += 1
            continue

        if not job_url:
            skipped += 1
            continue

        # Fetch and scrape job description
        try:
            resp = requests.get(job_url, headers=_HEADERS, timeout=15, allow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")
            description = soup.get_text(separator=" ", strip=True)[:_DESC_MAX_CHARS]
        except Exception as e:
            print(f"ERROR [scorer] Failed to fetch {job_url}: {e}")
            errors += 1
            continue

        # Extract title from "Company / Title / Year" name format
        parts = name.split(" / ")
        title = parts[1] if len(parts) >= 2 else name

        score = score_opportunity(title, description)
        if score is None:
            errors += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] Would score {name}: {score}")
        else:
            try:
                notion.update_fit_score(page_id, score)
            except Exception as e:
                print(f"ERROR [scorer] Failed to update Notion for {name}: {e}")
                errors += 1
                continue
            print(f"SCORED {name}: {score}")

        scored += 1
        time.sleep(1)

    return {"scored": scored, "skipped": skipped, "errors": errors}
