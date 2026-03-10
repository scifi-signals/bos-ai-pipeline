"""Mine Google Trends for trending science/health topics.

Two strategies:
1. Google Trends RSS feed (public, reliable, never blocked) — daily trending searches
2. pytrends related queries (unofficial, often rate-limited) — rising queries for
   science/health seed terms. Best-effort; returns 0 if Google blocks.

Every signal has a shareable Google Trends URL.
No API key required. Runs once daily with aggressive caching.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import unescape

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


def mine_trending_searches():
    """Extract trending science/health topics from Google Trends.

    Returns list of candidate dicts matching the discovery pipeline format.
    """
    # Check cache
    cached = _load_cache()
    if cached is not None:
        print(f"    Using cached Trends data ({len(cached)} topics)")
        return cached

    candidates = []
    seen_queries = set()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Strategy 1: RSS feed (reliable — never blocked by Google)
    rss_candidates = _fetch_rss_trends(today, seen_queries)
    candidates.extend(rss_candidates)
    print(f"    Google Trends RSS: {len(rss_candidates)} science/health topics from daily trending")

    # Strategy 2: pytrends related queries (best-effort — often rate-limited)
    pytrends_candidates = _fetch_pytrends_related(today, seen_queries)
    candidates.extend(pytrends_candidates)
    print(f"    Google Trends pytrends: {len(pytrends_candidates)} related queries (best-effort)")

    # Sort by signal strength
    candidates.sort(key=lambda c: c.get("signal_strength", 0), reverse=True)

    # Cap at top 30 to avoid noise
    candidates = candidates[:30]

    # Cache results (even if 0 — prevents re-hitting Google every run)
    _save_cache(candidates)

    return candidates


def _fetch_rss_trends(today, seen_queries):
    """Fetch daily trending searches from Google Trends RSS feed.

    This is a public XML feed that never gets rate-limited.
    Returns only items that pass the science/health filter.
    """
    candidates = []
    url = "https://trends.google.com/trending/rss?geo=US"

    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)

        # RSS items are in channel/item
        ns = {"ht": "https://trends.google.com/trending/rss"}
        for item in root.findall(".//item"):
            title_el = item.find("title")
            if title_el is None or not title_el.text:
                continue
            title = unescape(title_el.text.strip())

            # Get approximate traffic
            traffic_el = item.find("ht:approx_traffic", ns)
            traffic = 0
            if traffic_el is not None and traffic_el.text:
                traffic = int(re.sub(r"[^\d]", "", traffic_el.text) or "0")

            # Get related news titles for better keyword matching
            news_titles = []
            for news_item in item.findall("ht:news_item", ns):
                news_title_el = news_item.find("ht:news_item_title", ns)
                if news_title_el is not None and news_title_el.text:
                    news_titles.append(unescape(news_title_el.text.strip()))

            # Check if the trend OR its related news are science/health
            all_text = title + " " + " ".join(news_titles)
            if title.lower() not in seen_queries and _is_science_health(all_text):
                seen_queries.add(title.lower())
                candidates.append({
                    "raw_text": title,
                    "source_type": "trends",
                    "source": "Google Trends (daily trending)",
                    "source_url": _build_trends_url(title),
                    "date": today,
                    "signal_strength": max(traffic // 100, 50),
                    "trend_type": "daily",
                })

    except (URLError, ET.ParseError) as e:
        print(f"    Google Trends RSS failed: {e}")
    except Exception as e:
        print(f"    Google Trends RSS unexpected error: {e}")

    return candidates


def _fetch_pytrends_related(today, seen_queries):
    """Best-effort: use pytrends to get related queries for science seed terms.

    Often rate-limited by Google (429). Returns empty list on failure.
    Uses longer delays between queries to reduce blocking.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return []

    # Patch urllib3 compatibility: pytrends uses deprecated 'method_whitelist'
    # which was removed in urllib3 2.x (renamed to 'allowed_methods')
    try:
        import urllib3
        _orig_retry_init = urllib3.Retry.__init__

        def _patched_retry_init(self, *args, **kwargs):
            if "method_whitelist" in kwargs:
                kwargs["allowed_methods"] = kwargs.pop("method_whitelist")
            return _orig_retry_init(self, *args, **kwargs)

        urllib3.Retry.__init__ = _patched_retry_init
    except Exception:
        pass

    candidates = []

    try:
        pytrends = TrendReq(hl="en-US", tz=300, retries=2, backoff_factor=1.0)
    except Exception as e:
        print(f"    pytrends init failed: {e}")
        return []

    consecutive_failures = 0

    for seed in SEED_QUERIES:
        if consecutive_failures >= 2:
            print(f"    pytrends: 2 consecutive failures, stopping (likely rate-limited)")
            break
        try:
            time.sleep(5)  # Longer delay to reduce rate limiting
            pytrends.build_payload([seed], timeframe="now 7-d", geo="US")
            related = pytrends.related_queries()
            consecutive_failures = 0

            for term_data in related.values():
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
            consecutive_failures += 1
            err_short = str(e).split("(Caused by")[0].strip() if "(Caused by" in str(e) else str(e)[:80]
            print(f"    pytrends '{seed}' failed ({consecutive_failures}/2): {err_short}")
            continue

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
