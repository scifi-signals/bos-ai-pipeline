"""Find relevant NASEM publications for any question using the STM catalog."""

import json
import os
import re
from pathlib import Path

from config import PROJECT_DIR

# STM data paths — override via env vars for CI/server, defaults for local dev
STM_DIR = Path(os.environ.get("STM_DIR", r"C:\Users\chris\Downloads\science-trend-monitor"))
NASEM_CATALOG = STM_DIR / "nasem_catalog.json"
VERIFIED_DB = STM_DIR / "verified_nasem_database.json"

# Multi-word phrase patterns to detect in questions
PHRASE_PATTERNS = [
    # Climate & environment
    "global warming", "climate change", "air quality", "air pollution",
    "greenhouse gas", "sea level", "fossil fuel", "renewable energy",
    "carbon dioxide", "carbon emissions", "wildfire smoke", "particulate matter",
    "ozone layer", "ground-level ozone", "extreme weather", "water quality",
    "solar energy", "wind energy", "electric vehicle", "nuclear energy",
    # Health — general
    "public health", "mental health", "infectious disease", "chronic disease",
    "heart disease", "breathing problems", "respiratory illness", "lung disease",
    "birth weight", "premature death", "life expectancy", "food safety",
    # Vaccines & immunization
    "vaccine safety", "vaccine efficacy", "herd immunity", "mrna vaccine",
    "flu vaccine", "covid vaccine", "childhood immunization", "immunization schedule",
    # Pharmacy & medications
    "prescription drug", "drug safety", "drug pricing", "opioid crisis",
    "opioid use disorder", "opioid overdose", "medication safety",
    "pediatric medication", "off-label use", "weight loss drug",
    # Specific health topics
    "weight loss", "blood clot", "hiv prevention", "opioid epidemic",
    "substance abuse", "substance use", "alcohol use", "tobacco use",
    "screen time", "sleep deprivation", "noise pollution",
    # Technology & AI
    "artificial intelligence", "machine learning", "gene editing",
    "genetic testing", "medical imaging", "diagnostic accuracy",
    # Nutrition & diet
    "dietary supplement", "food additive", "processed food", "organic food",
    "genetically modified", "genetically engineered", "artificial sweetener",
    "food allergy", "food allergies", "food sensitivity",
    # Specific medical
    "blood clot", "blood clots", "hepatitis b",
    "thimerosal", "sleep deprivation",
    "anti-aging", "aging supplement",
    # Space & discovery
    "extraterrestrial", "uap", "ufo",
]

# Synonym expansion — maps trigger words to search terms
SYNONYMS = {
    # Climate
    "global warming": ["climate change", "climate", "warming", "greenhouse", "carbon"],
    "climate change": ["global warming", "climate", "warming", "greenhouse", "carbon"],
    "breathing": ["respiratory", "lung", "asthma", "copd", "air quality", "air pollution", "ozone"],
    "respiratory": ["breathing", "lung", "asthma", "copd", "air quality", "pulmonary"],
    "air quality": ["ozone", "smog", "particulate", "air pollution", "wildfire", "pm2.5"],
    "pollution": ["air quality", "ozone", "smog", "particulate", "emissions", "pollutant"],
    "wildfire": ["fire", "smoke", "air quality", "particulate", "drought"],
    "water": ["ocean", "drought", "flooding", "sea level", "freshwater"],
    "energy": ["solar", "wind", "nuclear", "renewable", "fossil fuel", "battery"],
    # Vaccines & immunization
    "vaccine": ["immunization", "vaccination", "mrna", "inoculation", "immunize"],
    "vaccination": ["vaccine", "immunization", "inoculation", "mrna"],
    "immunization": ["vaccine", "vaccination", "inoculation"],
    "mrna": ["vaccine", "moderna", "pfizer", "rna"],
    # Pharmacy & medications
    "pharmacist": ["pharmacy", "pharmacies", "dispensing", "prescription"],
    "pharmacy": ["pharmacist", "pharmacies", "drugstore", "dispensing"],
    "opioid": ["fentanyl", "heroin", "morphine", "oxycodone", "naloxone", "narcan", "overdose"],
    "naloxone": ["narcan", "opioid", "overdose", "reversal"],
    "narcan": ["naloxone", "opioid", "overdose"],
    "ozempic": ["semaglutide", "glp-1", "wegovy", "weight loss", "obesity"],
    "semaglutide": ["ozempic", "glp-1", "wegovy", "weight loss"],
    "obesity": ["weight", "overweight", "bmi", "diet", "metabolic"],
    # Health topics
    "cancer": ["tumor", "carcinoma", "oncology", "leukemia", "malignant"],
    "genetics": ["dna", "crispr", "genome", "gene editing", "genomics"],
    "nutrition": ["diet", "food", "obesity", "fasting", "dietary"],
    "mental health": ["depression", "anxiety", "behavioral", "stress", "ptsd", "psychiatric"],
    "depression": ["mental health", "anxiety", "psychiatric", "antidepressant"],
    "hiv": ["aids", "antiretroviral", "prep", "prevention"],
    "prep": ["hiv", "prevention", "prophylaxis", "truvada"],
    "pediatric": ["children", "child", "infant", "neonatal", "adolescent"],
    "children": ["pediatric", "child", "infant", "youth", "adolescent"],
    "blood clot": ["thrombosis", "embolism", "coagulation", "anticoagulant"],
    "diabetes": ["insulin", "glucose", "blood sugar", "metabolic", "a1c"],
    # AI & technology
    "artificial intelligence": ["machine learning", "deep learning", "neural network", "algorithm"],
    "machine learning": ["artificial intelligence", "deep learning", "algorithm", "neural"],
    "diagnostic": ["diagnosis", "screening", "detection", "imaging"],
    "mri": ["imaging", "magnetic resonance", "radiology", "scan"],
    # Diet & supplements
    "supplement": ["vitamin", "mineral", "herbal", "dietary supplement"],
    "organic": ["pesticide", "conventional", "farming", "agriculture"],
    "gmo": ["genetically modified", "genetically engineered", "transgenic", "bioengineered", "ge crop"],
    "allergy": ["allergen", "allergic", "anaphylaxis", "ige", "hypersensitivity"],
    "food allergy": ["allergen", "allergic reaction", "anaphylaxis", "peanut allergy"],
    "aging": ["longevity", "lifespan", "senescence", "gerontology"],
    "twin": ["twins", "monozygotic", "dizygotic", "identical twin"],
    "sleep": ["circadian", "insomnia", "melatonin", "sleep deprivation"],
    "altitude": ["hypoxia", "high altitude", "elevation"],
    "thimerosal": ["mercury", "preservative", "ethylmercury", "vaccine preservative"],
    "hepatitis": ["hepatitis b", "hbv", "liver disease", "viral hepatitis"],
    "extraterrestrial": ["uap", "ufo", "unidentified aerial", "alien"],
    "organoid": ["organoids", "stem cell", "tissue engineering", "in vitro"],
    "quantum": ["quantum biology", "quantum computing", "quantum effect", "entanglement"],
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

I have a list of NASEM publications. I need to know which ones — if any — contain
evidence that DIRECTLY helps answer this specific question.

For EACH publication, apply this test:
"If I opened this publication and searched for '{question.rstrip("?")}',
would I find relevant data, analysis, or expert conclusions?"

REJECT a publication if:
- It shares a keyword but covers a different topic (e.g., "Dietary Reference Intakes"
  is about nutrient requirements, NOT food allergies or food testing)
- It is about a different domain entirely (e.g., "AI and Future of Work" for a medical question)
- It is tangentially related at best (same broad field but different specific topic)
- Its title and description don't suggest it covers the question's core subject matter

It is VERY COMMON for none of the candidates to be relevant. Do not force matches.
Returning NONE is the correct answer when no publication genuinely fits.

Publications:
{pub_list}

First, write one sentence about what this question is actually asking about.
Then list ONLY the numbers of publications that pass the test, separated by commas.
If none pass: write NONE

Format:
TOPIC: [one sentence]
RESULT: [numbers or NONE]"""

    try:
        print(f"  LLM reranking {len(candidates)} candidates...")
        response = ask_claude(prompt, max_tokens=300)
        print(f"  LLM response: {response.strip()[:150]}")

        # Extract the RESULT line
        result_line = ""
        for line in response.strip().split("\n"):
            if line.strip().upper().startswith("RESULT"):
                result_line = line.strip()
                break

        # If no RESULT line found, don't parse random numbers from reasoning text
        if not result_line:
            if "NONE" in response.upper():
                print("  LLM says no relevant publications found")
                return []
            # No RESULT line and no NONE — treat as failed parse
            print("  LLM response missing RESULT line, treating as no results")
            return []

        if "NONE" in result_line.upper():
            print("  LLM says no relevant publications found")
            return []

        numbers = [int(n.strip()) for n in re.findall(r'\d+', result_line)]
        reranked = []
        seen = set()
        for n in numbers:
            if 1 <= n <= len(candidates) and n not in seen:
                seen.add(n)
                score, pub = candidates[n - 1]
                reranked.append((score, pub))
        if reranked:
            return reranked[:max_results]
        else:
            print("  LLM returned no valid publication numbers")
            return []
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


GENERIC_WORDS = {
    "health", "risk", "risks", "safety", "policy", "system", "research",
    "science", "study", "report", "review", "assessment", "evidence",
    "public", "national", "community", "care", "medical", "clinical",
    "disease", "prevention", "treatment", "children", "population",
    "food", "foods", "human", "people", "age", "impact", "effects",
    "education", "practice", "quality", "strategy", "program",
}


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

    # Track what kind of keywords matched (specific vs generic)
    specific_matches = 0
    generic_only = True

    # Phrase matches in title (highest weight — very specific)
    for phrase in phrases:
        if phrase in title:
            score += 10.0
            specific_matches += 1
            generic_only = False

    # Phrase matches in description/keywords
    for phrase in phrases:
        if phrase in desc:
            score += 4.0
            specific_matches += 1
            generic_only = False
        if phrase in pub_keywords:
            score += 3.0
            specific_matches += 1
            generic_only = False

    # Single words from the question (NOT expanded) in title — strong signal
    for word in single_words:
        if word in GENERIC_WORDS:
            continue
        if word in title:
            score += 4.0
            specific_matches += 1
            generic_only = False

    # Expanded keyword matches in title (weaker than direct words)
    for kw in expanded_keywords:
        if kw in phrases or kw in single_words:
            continue  # Already scored above
        if kw in GENERIC_WORDS:
            continue
        if kw in title:
            score += 2.0 if len(kw) >= 6 else 1.0
            specific_matches += 1
            generic_only = False

    # Expanded keyword matches in description (light weight)
    for kw in expanded_keywords:
        if kw in phrases:
            continue
        if kw in GENERIC_WORDS:
            continue
        if kw in desc:
            score += 0.3

    # Expanded keyword matches in pub keywords
    for kw in expanded_keywords:
        if kw in GENERIC_WORDS:
            continue
        if kw in pub_keywords:
            score += 0.3

    # If ONLY generic words matched, this pub is probably not relevant
    if generic_only and score > 0:
        score *= 0.1

    # Multi-keyword density bonus — only count specific matches
    specific_in_searchable = sum(1 for kw in expanded_keywords
                                  if kw not in GENERIC_WORDS and kw in searchable)
    if specific_in_searchable >= 5:
        score += 3.0
    elif specific_in_searchable >= 3:
        score += 1.5

    # Cross-domain intersection bonus: if question spans domains (e.g. climate + health),
    # strongly reward pubs that match terms from BOTH domains
    if phrases and len(phrases) >= 2:
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
            score += 8.0

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
