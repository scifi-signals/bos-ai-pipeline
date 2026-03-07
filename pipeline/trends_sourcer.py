"""Mine Google Trends for trending science/health topics.

Uses pytrends (unofficial) to detect search interest spikes in science
and health categories. Every signal has a shareable Google Trends URL.

No API key required. Runs once daily with aggressive caching.
Graceful fallback if Google blocks requests.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

# Cache file to avoid redundant API calls
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_FILE = CACHE_DIR / "trends_cache.json"
CACHE_MAX_AGE_HOURS = 20  # Re-fetch once per day at most

# Seed queries — broad science/health terms that surface trending sub-topics
SEED_QUERIES = [
    "health risk",
    "is it safe",
    "does cause cancer",
    "vaccine side effects",
    "nutrition myth",
    "climate change effects",
    "air pollution health",
    "water contamination",
    "food safety",
    "mental health",
]

# Google Trends category IDs
# 45 = Health, 174 = Science, 71 = Food & Drink
CATEGORY_IDS = [45, 174]


def mine_trending_searches():
    """Extract trending science/health topics from Google Trends.

    Returns list of candidate dicts matching the discovery pipeline format:
    - raw_text: the trending topic/query
    - source_type: "trends"
    - source: "Google Trends"
    - source_url: shareable Google Trends URL
    - date: today's date
    - signal_strength: relative interest score
    """
    # Check cache
    cached = _load_cache()
    if cached is not None:
        print(f"    Using cached Trends data ({len(cached)} topics)")
        return cached

    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("    pytrends not installed — skipping Google Trends (pip install pytrends)")
        return []

    candidates = []
    seen_queries = set()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        pytrends = TrendReq(hl="en-US", tz=300, retries=2, backoff_factor=1.0)
    except Exception as e:
        print(f"    Google Trends init failed: {e}")
        return []

    # Strategy 1: Related queries for seed terms (finds what people are ACTUALLY searching)
    for seed in SEED_QUERIES:
        try:
            pytrends.build_payload([seed], timeframe="now 7-d", geo="US")
            related = pytrends.related_queries()

            for term_data in related.values():
                # "rising" queries show what's spiking — most valuable
                rising = term_data.get("rising")
                if rising is not None and not rising.empty:
                    for _, row in rising.head(5).iterrows():
                        query = str(row.get("query", "")).strip()
                        value = row.get("value", 0)
                        if query and query.lower() not in seen_queries and _is_science_health(query):
                            seen_queries.add(query.lower())
                            candidates.append({
                                "raw_text": query,
                                "source_type": "trends",
                                "source": "Google Trends (rising)",
                                "source_url": _build_trends_url(query),
                                "date": today,
                                "signal_strength": min(int(value), 1000),
                                "trend_type": "rising",
                            })

                # "top" queries show sustained interest
                top = term_data.get("top")
                if top is not None and not top.empty:
                    for _, row in top.head(3).iterrows():
                        query = str(row.get("query", "")).strip()
                        value = row.get("value", 0)
                        if query and query.lower() not in seen_queries and _is_science_health(query):
                            seen_queries.add(query.lower())
                            candidates.append({
                                "raw_text": query,
                                "source_type": "trends",
                                "source": "Google Trends (top)",
                                "source_url": _build_trends_url(query),
                                "date": today,
                                "signal_strength": int(value),
                                "trend_type": "top",
                            })

        except Exception as e:
            # Google may rate-limit or block — this is expected
            print(f"    Trends query '{seed}' failed: {e}")
            continue

    # Strategy 2: Trending searches (daily trending topics)
    try:
        trending = pytrends.trending_searches(pn="united_states")
        if trending is not None and not trending.empty:
            for _, row in trending.head(20).iterrows():
                query = str(row.iloc[0]).strip() if len(row) > 0 else ""
                if query and query.lower() not in seen_queries and _is_science_health(query):
                    seen_queries.add(query.lower())
                    candidates.append({
                        "raw_text": query,
                        "source_type": "trends",
                        "source": "Google Trends (daily trending)",
                        "source_url": _build_trends_url(query),
                        "date": today,
                        "signal_strength": 50,  # Trending but no specific score
                        "trend_type": "daily",
                    })
    except Exception as e:
        print(f"    Daily trending failed: {e}")

    # Sort by signal strength
    candidates.sort(key=lambda c: c.get("signal_strength", 0), reverse=True)

    # Cap at top 30 to avoid noise
    candidates = candidates[:30]

    # Cache results
    _save_cache(candidates)

    return candidates


def _build_trends_url(query):
    """Build a shareable Google Trends URL for a query."""
    encoded = query.replace(" ", "%20")
    return f"https://trends.google.com/trends/explore?q={encoded}&geo=US&date=now%207-d"


def _is_science_health(query):
    """Filter for science/health related queries. Rejects entertainment, sports, politics."""
    query_lower = query.lower()

    # Reject patterns
    reject_patterns = [
        r'\b(nfl|nba|mlb|nhl|football|basketball|baseball|hockey)\b',
        r'\b(movie|film|actor|actress|celebrity|singer|album|concert)\b',
        r'\b(election|democrat|republican|trump|biden|congress)\b',
        r'\b(stock|crypto|bitcoin|ethereum|trading)\b',
        r'\b(game|gaming|xbox|playstation|nintendo)\b',
    ]
    for pattern in reject_patterns:
        if re.search(pattern, query_lower):
            return False

    # Accept patterns — science/health keywords
    accept_patterns = [
        r'\b(health|medical|disease|virus|cancer|vaccine|drug|medication)\b',
        r'\b(study|research|scientist|clinical|trial|evidence)\b',
        r'\b(diet|nutrition|food|supplement|vitamin|organic)\b',
        r'\b(climate|pollution|environment|emission|carbon)\b',
        r'\b(mental health|anxiety|depression|sleep|stress)\b',
        r'\b(safe|risk|danger|toxic|contamination|exposure)\b',
        r'\b(brain|heart|lung|blood|immune|gut|microbiome)\b',
        r'\b(fda|cdc|who|nih|epa)\b',
        r'\b(recall|outbreak|warning|alert|ban)\b',
    ]
    for pattern in accept_patterns:
        if re.search(pattern, query_lower):
            return True

    # If no strong signal either way, reject (reduces noise)
    return False


def _load_cache():
    """Load cached Trends results if fresh enough."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        if datetime.utcnow() - cached_at < timedelta(hours=CACHE_MAX_AGE_HOURS):
            return data.get("candidates", [])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _save_cache(candidates):
    """Cache Trends results to avoid redundant API calls."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "cached_at": datetime.utcnow().isoformat(),
        "candidates": candidates,
    }
    CACHE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
