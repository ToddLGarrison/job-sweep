import anthropic

from config import ANTHROPIC_API_KEY

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """\
You are preparing a pre-interview research brief for Todd Garrison, who has
an interview coming up for a {title} role at {company}.

Research the following and write a structured plain-text brief:

1. COMPANY SNAPSHOT
   - What the company does (2-3 sentences, specific product/value prop)
   - Business model (SaaS, usage-based, marketplace, etc.)
   - Company stage (Series X, public, private, headcount if findable)
   - Recent funding (amount, date, investors if available)

2. RECENT NEWS (last 90 days)
   - Product launches, major announcements
   - Leadership changes
   - Layoffs, acquisitions, or restructuring
   - Any signals about company health or trajectory

3. PRODUCT & ICP
   - Primary product(s) and what problem they solve
   - Ideal customer profile (who buys this)
   - Key differentiators vs competitors

4. COMPETITIVE LANDSCAPE
   - 3-4 main competitors
   - How this company positions against them

5. CULTURE SIGNALS
   - Glassdoor rating if findable (do not fabricate)
   - Any public signals about engineering/CS culture
   - Remote/hybrid stance if public

6. HIRING MANAGER
   - Search LinkedIn and the web for the likely hiring manager for a
     {title} role at {company}
   - Report: name, title, LinkedIn URL if found, how long at company,
     any public content (talks, posts, articles) that reveals their
     priorities or style
   - If not findable, say so explicitly — do not guess

7. SMART QUESTIONS TO ASK
   - 3 questions Todd should ask based specifically on this research
   - Must reference specific findings, not generic interview questions

Use web search for all of this. Do not fabricate metrics, funding amounts,
or people. If something is not findable, say "Not found" rather than guessing.

Format with clear section headers. Keep each section tight — this is a brief,
not an essay. Total length should be 600-900 words."""


def generate_brief(company: str, title: str, job_url: str) -> str:
    """Research company via Claude with web_search and return a formatted brief."""
    system = _SYSTEM_PROMPT.format(company=company, title=title)
    user_content = f"Company: {company}\nRole: {title}\nJob URL: {job_url}"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=3000,
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as e:
        raise RuntimeError(f"Claude API call failed: {e}") from e

    text_parts = [
        block.text
        for block in response.content
        if hasattr(block, "type") and block.type == "text"
    ]
    brief = "\n".join(text_parts).strip()
    if not brief:
        raise RuntimeError("Claude returned no text content in response")
    return brief
