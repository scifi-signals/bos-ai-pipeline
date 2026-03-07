"""Mine Reddit for public science questions and misconceptions.

Searches science/health subreddits for posts that indicate public confusion
or misinformation. Every signal has a permanent Reddit URL for verification.

Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars (free tier OAuth).
"""

import json
import os
import time
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
    # Check if PRAW credentials are available
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("    REDDIT_CLIENT_ID/SECRET not set — skipping Reddit source")
        return []

    # Check cache
    cached = _load_cache()
    if cached is not None:
        print(f"    Using cached Reddit data ({len(cached)} posts)")
        return cached

    try:
        import praw
    except ImportError:
        print("    praw not installed — skipping Reddit source (pip install praw)")
        return []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="BoS-Pipeline/1.0 (science misinformation research)",
        )
        # Verify connection with read-only mode
        reddit.read_only = True
    except Exception as e:
        print(f"    Reddit auth failed: {e}")
        return []

    candidates = []
    seen_urls = set()
    cutoff = datetime.utcnow() - timedelta(days=MAX_POST_AGE_DAYS)

    # Strategy 1: Search across subreddits with misinformation-related queries
    for query in SEARCH_QUERIES:
        try:
            results = reddit.subreddit("+".join(SUBREDDITS)).search(
                query, sort="relevance", time_filter="month",
                limit=MAX_RESULTS_PER_QUERY
            )
            for post in results:
                _process_post(post, candidates, seen_urls, cutoff)
        except Exception as e:
            print(f"    Search '{query}' failed: {e}")
            continue

    # Strategy 2: Hot posts from key subreddits
    for sub_name in ["IsItBullshit", "askscience", "nutrition"]:
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.hot(limit=25):
                _process_post(post, candidates, seen_urls, cutoff)
        except Exception as e:
            print(f"    r/{sub_name} hot failed: {e}")
            continue

    # Sort by signal strength (engagement)
    candidates.sort(key=lambda c: c.get("signal_strength", 0), reverse=True)

    # Cache results
    _save_cache(candidates)

    return candidates


def _process_post(post, candidates, seen_urls, cutoff):
    """Process a single Reddit post into a candidate if it meets criteria."""
    # Skip if already seen, too old, or too low engagement
    url = f"https://www.reddit.com{post.permalink}"
    if url in seen_urls:
        return
    seen_urls.add(url)

    if post.score < MIN_UPVOTES:
        return

    created = datetime.utcfromtimestamp(post.created_utc)
    if created < cutoff:
        return

    # Skip pinned/stickied moderator posts
    if post.stickied:
        return

    title = post.title.strip()
    if len(title) < 15:
        return

    # Combine title + selftext for context (truncated)
    raw_text = title
    if post.selftext and len(post.selftext) > 20:
        body_preview = post.selftext[:200].replace("\n", " ").strip()
        raw_text = f"{title} — {body_preview}"

    candidates.append({
        "raw_text": raw_text,
        "source_type": "reddit",
        "source": f"r/{post.subreddit.display_name}",
        "source_url": url,
        "date": created.strftime("%Y-%m-%d"),
        "signal_strength": _compute_signal_strength(post),
        "upvotes": post.score,
        "comments": post.num_comments,
    })


def _compute_signal_strength(post):
    """Score a post's relevance based on engagement metrics."""
    # Upvotes matter most, but high comment counts indicate active debate
    score = post.score
    if post.num_comments > 50:
        score *= 1.5
    if post.num_comments > 200:
        score *= 2.0
    # Upvote ratio < 0.7 means controversial (people disagree = confusion)
    if hasattr(post, 'upvote_ratio') and post.upvote_ratio < 0.7:
        score *= 1.3
    return round(score)


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
