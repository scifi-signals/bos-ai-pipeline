"""Mine Reddit for public science questions and misconceptions.

Searches science/health subreddits for posts that indicate public confusion
or misinformation. Every signal has a permanent Reddit URL for verification.

Uses Reddit's public JSON API (no authentication required).
Rate-limited to ~1 request/second to stay within unauthenticated limits.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Cache file to avoid redundant API calls
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_FILE = CACHE_DIR / "reddit_cache.json"
CACHE_MAX_AGE_HOURS = 20  # Re-fetch once per day at most

# Subreddits most likely to contain public science confusion
SUBREDDITS = [
    "IsItBullshit",       # Directly asks "is this claim true?"
    "askscience",         # Public science questions
    "nutrition",          # Diet/health misconceptions
    "science",            # General science discussion
    "Health",             # Health concerns
    "NoStupidQuestions",  # Genuine public confusion
    "explainlikeimfive",  # Public trying to understand science
]

# Search queries targeting misinformation patterns
SEARCH_QUERIES = [
    "is it true that",
    "myth or fact",
    "does science say",
    "debunked",
    "misinformation",
    "is it safe to",
    "does cause cancer",
    "health risk",
    "scientific consensus",
]

# Minimum engagement to filter noise
MIN_UPVOTES = 10
MAX_POST_AGE_DAYS = 30
MAX_RESULTS_PER_QUERY = 10

USER_AGENT = "BoS-Pipeline/1.0 (science misinformation research)"
REQUEST_DELAY = 1.5  # seconds between requests to respect rate limits


def mine_reddit_questions():
    """Extract science questions/misconceptions from Reddit.

    Returns list of candidate dicts matching the discovery pipeline format:
    - raw_text: the question or claim
    - source_type: "reddit"
    - source: subreddit name
    - source_url: permanent Reddit post URL
    - date: post date
    - signal_strength: based on upvotes/comments
    """
    # Check cache
    cached = _load_cache()
    if cached is not None:
        print(f"    Using cached Reddit data ({len(cached)} posts)")
        return cached

    candidates = []
    seen_urls = set()
    cutoff = datetime.utcnow() - timedelta(days=MAX_POST_AGE_DAYS)

    # Strategy 1: Search across subreddits with misinformation-related queries
    multi_sub = "+".join(SUBREDDITS)
    for query in SEARCH_QUERIES:
        try:
            posts = _reddit_search(multi_sub, query)
            for post in posts[:MAX_RESULTS_PER_QUERY]:
                _process_post(post, candidates, seen_urls, cutoff)
        except Exception as e:
            print(f"    Search '{query}' failed: {e}")
            continue

    # Strategy 2: Hot posts from key subreddits
    for sub_name in ["IsItBullshit", "askscience", "nutrition"]:
        try:
            posts = _reddit_hot(sub_name, limit=25)
            for post in posts:
                _process_post(post, candidates, seen_urls, cutoff)
        except Exception as e:
            print(f"    r/{sub_name} hot failed: {e}")
            continue

    # Sort by signal strength (engagement)
    candidates.sort(key=lambda c: c.get("signal_strength", 0), reverse=True)

    # Cache results
    _save_cache(candidates)

    print(f"    Reddit: {len(candidates)} posts found")
    return candidates


def _reddit_get(url):
    """Fetch a Reddit JSON endpoint with rate limiting and error handling."""
    time.sleep(REQUEST_DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            # Rate limited — wait and retry once
            retry_after = int(e.headers.get("Retry-After", "10"))
            print(f"    Reddit rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise


def _reddit_search(subreddit, query):
    """Search a subreddit (or multi-sub) via public JSON API."""
    encoded_query = urllib.request.quote(query)
    url = f"https://www.reddit.com/r/{subreddit}/search.json?q={encoded_query}&sort=relevance&t=month&restrict_sr=on&limit=25"
    data = _reddit_get(url)
    return [child["data"] for child in data.get("data", {}).get("children", [])]


def _reddit_hot(subreddit, limit=25):
    """Get hot posts from a subreddit via public JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    data = _reddit_get(url)
    return [child["data"] for child in data.get("data", {}).get("children", [])]


def _process_post(post, candidates, seen_urls, cutoff):
    """Process a single Reddit post dict into a candidate if it meets criteria."""
    permalink = post.get("permalink", "")
    url = f"https://www.reddit.com{permalink}"
    if url in seen_urls:
        return
    seen_urls.add(url)

    score = post.get("score", 0)
    if score < MIN_UPVOTES:
        return

    created_utc = post.get("created_utc", 0)
    created = datetime.utcfromtimestamp(created_utc)
    if created < cutoff:
        return

    # Skip pinned/stickied moderator posts
    if post.get("stickied", False):
        return

    title = (post.get("title") or "").strip()
    if len(title) < 15:
        return

    # Combine title + selftext for context (truncated)
    raw_text = title
    selftext = (post.get("selftext") or "").strip()
    if len(selftext) > 20:
        body_preview = selftext[:200].replace("\n", " ").strip()
        raw_text = f"{title} — {body_preview}"

    num_comments = post.get("num_comments", 0)
    upvote_ratio = post.get("upvote_ratio", 1.0)
    subreddit_name = post.get("subreddit", "unknown")

    candidates.append({
        "raw_text": raw_text,
        "source_type": "reddit",
        "source": f"r/{subreddit_name}",
        "source_url": url,
        "date": created.strftime("%Y-%m-%d"),
        "signal_strength": _compute_signal_strength(score, num_comments, upvote_ratio),
        "upvotes": score,
        "comments": num_comments,
    })


def _compute_signal_strength(score, num_comments, upvote_ratio):
    """Score a post's relevance based on engagement metrics."""
    strength = score
    if num_comments > 50:
        strength *= 1.5
    if num_comments > 200:
        strength *= 2.0
    # Upvote ratio < 0.7 means controversial (people disagree = confusion)
    if upvote_ratio < 0.7:
        strength *= 1.3
    return round(strength)


def _load_cache():
    """Load cached Reddit results if fresh enough."""
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
    """Cache Reddit results to avoid redundant API calls."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "cached_at": datetime.utcnow().isoformat(),
        "candidates": candidates,
    }
    CACHE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
