"""Find relevant NASEM publications for any question using the STM catalog."""

import json
import re
from pathlib import Path

from config import PROJECT_DIR

# STM data paths
STM_DIR = Path(r"C:\Users\chris\Downloads\science-trend-monitor")
NASEM_CATALOG = STM_DIR / "nasem_catalog.json"
VERIFIED_DB = STM_DIR / "verified_nasem_database.json"

# Multi-word phrase patterns to detect in questions
PHRASE_PATTERNS = [
    "global warming", "climate change", "air quality", "air pollution",
    "greenhouse gas", "sea level", "fossil fuel", "renewable energy",
    "mental health", "public health", "gene editing", "artificial intelligence",
    "machine learning", "food safety", "water quality", "nuclear energy",
    "solar energy", "wind energy", "electric vehicle", "carbon dioxide",
    "carbon emissions", "wildfire smoke", "particulate matter",
    "ozone layer", "ground-level ozone", "extreme weather",
    "infectious disease", "chronic disease", "heart disease",
    "breathing problems", "respiratory illness", "lung disease",
    "birth weight", "premature death", "life expectancy",
]

# Synonym expansion — maps trigger words to search terms
SYNONYMS = {
    "global warming": ["climate change", "climate", "warming", "greenhouse", "carbon"],
    "climate change": ["global warming", "climate", "warming", "greenhouse", "carbon"],
    "breathing": ["respiratory", "lung", "asthma", "copd", "air quality", "air pollution", "ozone"],
    "respiratory": ["breathing", "lung", "asthma", "copd", "air quality", "pulmonary"],
    "air quality": ["ozone", "smog", "particulate", "air pollution", "wildfire", "pm2.5"],
    "pollution": ["air quality", "ozone", "smog", "particulate", "emissions", "pollutant"],
    "wildfire": ["fire", "smoke", "air quality", "particulate", "drought"],
    "vaccine": ["immunization", "vaccination", "mrna"],
    "cancer": ["tumor", "carcinoma", "oncology", "leukemia"],
    "genetics": ["dna", "crispr", "genome", "gene editing", "genomics"],
    "nutrition": ["diet", "food", "obesity", "fasting"],
    "mental health": ["depression", "anxiety", "behavioral", "stress", "ptsd"],
    "water": ["ocean", "drought", "flooding", "sea level", "freshwater"],
    "energy": ["solar", "wind", "nuclear", "renewable", "fossil fuel", "battery"],
}


def find_nasem_sources(question, max_results=10, use_llm_rerank=True):
    """Find NASEM publications relevant to a question. Returns ranked list.

    Uses keyword scoring to find candidates, then optionally LLM reranking
    for cross-domain questions where keyword matching alone falls short.
    """
    catalog = _load_catalog()
    verified = _load_verified()

    # Extract keywords: phrases first, then individual words
    phrases, single_words = _extract_keywords(question)
    all_keywords = phrases + single_words
    expanded = _expand_keywords(all_keywords)
    print(f"  Phrases: {phrases}")
    print(f"  Words: {single_words}")
    print(f"  Expanded: {sorted(expanded)[:20]}{'...' if len(expanded) > 20 else ''}")

    # Score all publications
    scored = []
    for pub in catalog:
        score = _score_publication(pub, phrases, single_words, expanded,
                                   is_verified=str(pub.get("id", "")) in verified)
        if score > 0:
            scored.append((score, pub))

    scored.sort(key=lambda x: -x[0])

    # Take top candidates for LLM reranking
    candidates = scored[:max_results * 3]
    print(f"  Keyword scoring: {len(scored)} matches, top {len(candidates)} candidates")

    if use_llm_rerank and candidates:
        results = _llm_rerank(question, candidates, max_results)
    else:
        results = candidates[:max_results]

    for score, pub in results[:5]:
        print(f"    [{score:.1f}] {pub['title'][:80]} ({pub.get('year', '?')})")

    return [{
        "name": pub["title"],
        "url": pub["url"],
        "tier": 1,
        "type": "web",
        "score": round(score, 1),
        "year": pub.get("year"),
        "committee": pub.get("committee", ""),
        "description": pub.get("description", "")[:200],
    } for score, pub in results]


def _llm_rerank(question, candidates, max_results):
    """Use Claude to rerank candidates by relevance to the question."""
    from llm import ask_claude

    pub_list = ""
    for i, (score, pub) in enumerate(candidates):
        desc = (pub.get("description") or "")[:150]
        pub_list += f"{i+1}. [{score:.0f}] {pub['title']} ({pub.get('year', '?')})\n   {desc}\n"

    prompt = f"""Question: {question}

Rank these NASEM publications by relevance to answering this question.
Return ONLY the numbers of the top {max_results} most relevant publications, best first.
Consider: Does this publication contain evidence that directly addresses the question?
A publication about air quality + health is more relevant than one about carbon pricing.

Publications:
{pub_list}

Return format: just the numbers separated by commas, e.g.: 5,2,8,1,3"""

    try:
        print(f"  LLM reranking {len(candidates)} candidates...")
        response = ask_claude(prompt, max_tokens=200)
        numbers = [int(n.strip()) for n in re.findall(r'\d+', response)]
        reranked = []
        seen = set()
        for n in numbers:
            if 1 <= n <= len(candidates) and n not in seen:
                seen.add(n)
                score, pub = candidates[n - 1]
                reranked.append((score, pub))
        if reranked:
            return reranked[:max_results]
    except Exception as e:
        print(f"  LLM reranking failed ({e}), using keyword scores")

    return candidates[:max_results]


def _load_catalog():
    """Load NASEM catalog from STM project."""
    if not NASEM_CATALOG.exists():
        print(f"  WARNING: NASEM catalog not found at {NASEM_CATALOG}")
        return []
    data = json.loads(NASEM_CATALOG.read_text(encoding="utf-8"))
    return data.get("publications", [])


def _load_verified():
    """Load verified NASEM database IDs for boost scoring."""
    if not VERIFIED_DB.exists():
        return set()
    data = json.loads(VERIFIED_DB.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(p.get("id", "")) for p in data}
    elif isinstance(data, dict):
        return set(str(k) for k in data.keys())
    return set()


def _extract_keywords(question):
    """Extract multi-word phrases and single keywords from a question."""
    q_lower = question.lower()

    # Find matching phrases
    phrases = []
    for phrase in PHRASE_PATTERNS:
        if phrase in q_lower:
            phrases.append(phrase)

    # Extract remaining single words
    stop_words = {
        "does", "do", "is", "are", "can", "will", "how", "what", "why", "when",
        "the", "a", "an", "of", "in", "to", "for", "and", "or", "not", "with",
        "from", "by", "on", "at", "it", "its", "this", "that", "be", "have",
        "has", "had", "was", "were", "been", "being", "cause", "causes", "causing",
        "make", "makes", "making", "lead", "leads", "affect", "affects", "effect",
        "problem", "problems", "people", "human", "humans", "more", "about",
    }
    words = re.findall(r'\b[a-z]+\b', q_lower)
    # Remove words already captured in phrases
    phrase_words = set()
    for p in phrases:
        phrase_words.update(p.split())
    single_words = [w for w in words if w not in stop_words and w not in phrase_words and len(w) > 2]

    return phrases, single_words


def _expand_keywords(all_keywords):
    """Expand keywords using synonym map. Also expands individual words from phrases."""
    expanded = set(all_keywords)

    # Also break phrases into individual words for expansion
    all_terms = set(all_keywords)
    for kw in all_keywords:
        all_terms.update(kw.split())

    for kw in all_terms:
        if kw in SYNONYMS:
            expanded.update(SYNONYMS[kw])
        for trigger, synonyms in SYNONYMS.items():
            if kw in synonyms:
                expanded.update(synonyms)
                expanded.add(trigger)
    return list(expanded)


def _score_publication(pub, phrases, single_words, expanded_keywords, is_verified=False):
    """Score a publication against keywords. Higher = more relevant.

    NOTE: The catalog's 'topics' field is unreliable (all pubs have all 26 topics),
    so we only match against title, description, and keywords.
    """
    score = 0.0
    title = (pub.get("title") or "").lower()
    desc = (pub.get("description") or "").lower()
    pub_keywords = " ".join(k.lower() for k in (pub.get("keywords") or []))
    searchable = f"{title} {desc} {pub_keywords}"

    # Phrase matches in title (highest weight — very specific)
    for phrase in phrases:
        if phrase in title:
            score += 10.0

    # Phrase matches in description/keywords
    for phrase in phrases:
        if phrase in desc:
            score += 4.0
        if phrase in pub_keywords:
            score += 3.0

    # Expanded keyword matches in title
    for kw in expanded_keywords:
        if kw in phrases:
            continue  # Already scored above
        if kw in title:
            score += 3.0 if len(kw) >= 6 else 2.0

    # Expanded keyword matches in description
    for kw in expanded_keywords:
        if kw in phrases:
            continue
        if kw in desc:
            score += 0.5

    # Expanded keyword matches in pub keywords
    for kw in expanded_keywords:
        if kw in pub_keywords:
            score += 0.5

    # Multi-keyword density bonus: reward pubs matching many different terms
    matches = sum(1 for kw in expanded_keywords if kw in searchable)
    if matches >= 5:
        score += 3.0
    elif matches >= 3:
        score += 1.5

    # Cross-domain intersection bonus: if question spans domains (e.g. climate + health),
    # strongly reward pubs that match terms from BOTH domains
    if phrases and len(phrases) >= 2:
        # Check if pub matches terms related to each phrase
        phrase_matches = 0
        for phrase in phrases:
            phrase_terms = set()
            phrase_terms.add(phrase)
            for w in phrase.split():
                if w in SYNONYMS:
                    phrase_terms.update(SYNONYMS[w])
            if any(t in searchable for t in phrase_terms):
                phrase_matches += 1
        if phrase_matches >= 2:
            score += 8.0  # Big bonus for cross-domain relevance

    # Verified publication boost
    if is_verified:
        score += 5.0

    # Recency bonus
    year = pub.get("year")
    if year:
        if year >= 2024:
            score += 3.0
        elif year >= 2021:
            score += 2.0
        elif year >= 2016:
            score += 1.0

    return score


if __name__ == "__main__":
    import sys
    question = " ".join(sys.argv[1:]) or "Does global warming cause breathing problems?"
    print(f"\nFinding NASEM sources for: {question}\n")
    results = find_nasem_sources(question)
    print(f"\nTop {len(results)} results:")
    for r in results:
        print(f"  [{r['score']}] {r['name']}")
        print(f"       {r['url']}")
        print(f"       Year: {r['year']} | {r['description'][:80]}")
        print()
