"""Find alternative authoritative sources when NASEM has no coverage.

When the NASEM catalog has no relevant publications for a question,
this module identifies other authoritative sources (CDC, WHO, IPCC,
Cochrane, peer-reviewed meta-analyses) that could provide evidence.

This surfaces NASEM gaps as opportunities rather than silently dropping
questions where misinformation is actively circulating.
"""

import json
import re

from llm import ask_claude


# Known authority domains — used to validate Claude's suggestions
KNOWN_AUTHORITIES = {
    "CDC": {
        "full_name": "Centers for Disease Control and Prevention",
        "base_url": "https://www.cdc.gov",
        "tier": 2,
    },
    "WHO": {
        "full_name": "World Health Organization",
        "base_url": "https://www.who.int",
        "tier": 2,
    },
    "EPA": {
        "full_name": "Environmental Protection Agency",
        "base_url": "https://www.epa.gov",
        "tier": 2,
    },
    "FDA": {
        "full_name": "Food and Drug Administration",
        "base_url": "https://www.fda.gov",
        "tier": 2,
    },
    "NIH": {
        "full_name": "National Institutes of Health",
        "base_url": "https://www.nih.gov",
        "tier": 2,
    },
    "IPCC": {
        "full_name": "Intergovernmental Panel on Climate Change",
        "base_url": "https://www.ipcc.ch",
        "tier": 1,
    },
    "Cochrane": {
        "full_name": "Cochrane Library (systematic reviews)",
        "base_url": "https://www.cochranelibrary.com",
        "tier": 1,
    },
    "USGCRP": {
        "full_name": "U.S. Global Change Research Program",
        "base_url": "https://www.globalchange.gov",
        "tier": 2,
    },
    "HEI": {
        "full_name": "Health Effects Institute",
        "base_url": "https://www.healtheffects.org",
        "tier": 2,
    },
    "USDA": {
        "full_name": "U.S. Department of Agriculture",
        "base_url": "https://www.usda.gov",
        "tier": 2,
    },
}


def find_alternative_sources(question, max_results=5):
    """Find authoritative non-NASEM sources for a question.

    Returns a list of suggested sources with organization, description,
    and search guidance. Does NOT fabricate URLs — provides organization
    base URLs and specific document/page names to search for.
    """
    prompt = f"""Question: {question}

The National Academies (NASEM) has no publications that directly address this question.
Identify up to {max_results} specific, real, authoritative sources from OTHER organizations
that would contain evidence to answer this question.

RULES:
- Only suggest sources you are CONFIDENT actually exist (published reports, fact sheets, guidelines)
- Prefer: CDC, WHO, EPA, FDA, NIH, IPCC, Cochrane systematic reviews, USGCRP, major meta-analyses
- Be SPECIFIC — name the actual document, page, or guideline (not just "CDC has info on this")
- Do NOT invent URLs — just name the organization and the specific resource
- If you can't identify real specific sources, return NONE

Return as JSON array:
[
  {{
    "organization": "CDC",
    "resource_name": "Vaccines and Immunization: Myths and Facts",
    "description": "CDC's fact sheet directly addresses common vaccine misconceptions",
    "relevance": "Directly rebuts the specific misinformation claim with evidence"
  }}
]

Or if no reliable alternatives exist: NONE"""

    try:
        response = ask_claude(prompt, max_tokens=1000)
        stripped = response.strip()

        if "NONE" in stripped.upper() and len(stripped) < 20:
            return []

        # Extract JSON array from response
        match = re.search(r'\[.*\]', stripped, re.DOTALL)
        if not match:
            return []

        sources = json.loads(match.group())
        results = []
        for s in sources[:max_results]:
            org = s.get("organization", "")
            # Look up known authority info
            authority = KNOWN_AUTHORITIES.get(org, {})
            results.append({
                "organization": org,
                "organization_full": authority.get("full_name", org),
                "base_url": authority.get("base_url", ""),
                "tier": authority.get("tier", 3),
                "resource_name": s.get("resource_name", ""),
                "description": s.get("description", ""),
                "relevance": s.get("relevance", ""),
            })
        return results

    except Exception as e:
        print(f"    Alternative sourcing failed: {e}")
        return []
