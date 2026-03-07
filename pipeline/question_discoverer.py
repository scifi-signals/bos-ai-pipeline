"""Discover potential BoS questions from STM trending topics and podcast claims."""

import json
import os
import re
from pathlib import Path
from datetime import datetime

from config import PROJECT_DIR
from llm import ask_claude

# Data paths — override via env vars for CI/server, defaults for local dev
STM_DIR = Path(os.environ.get("STM_DIR", r"C:\Users\chris\Downloads\science-trend-monitor"))
PODCAST_DIR = Path(os.environ.get("PODCAST_DIR", r"C:\Users\chris\Downloads\science-podcast-monitor"))
PODCAST_SUMMARIES = PODCAST_DIR / "data" / "summaries"
TOPIC_HISTORY = STM_DIR / "topic_history.json"


def discover_questions(max_questions=10):
    """Mine questions from all available sources. Returns ranked list."""
    print("Discovering potential BoS questions...\n")

    raw_questions = []

    # Source 1: Podcast claims that need verification
    podcast_qs = _mine_podcast_claims()
    print(f"  Podcast claims: {len(podcast_qs)} candidates")

    # Source 2: STM trending topics + articles
    trending_qs = _mine_trending_topics()
    print(f"  Trending topics: {len(trending_qs)} candidates")

    # Interleave sources so both get represented in the candidate cap
    # Give STM articles priority slots since they're outnumbered by podcasts
    raw_questions.extend(trending_qs)
    raw_questions.extend(podcast_qs)

    if not raw_questions:
        print("  No candidates found. Check STM and podcast monitor data paths.")
        return []

    # Use Claude to rank and refine into BoS-style questions
    print(f"\n  Ranking {len(raw_questions)} candidates via Claude...")
    ranked = _rank_and_refine(raw_questions, max_questions)

    return ranked


def _mine_podcast_claims():
    """Extract verifiable claims from podcast episode summaries."""
    if not PODCAST_SUMMARIES.exists():
        return []

    candidates = []
    for summary_file in sorted(PODCAST_SUMMARIES.glob("*.json"), reverse=True)[:50]:
        try:
            data = json.loads(summary_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        podcast = data.get("podcast_name", summary_file.stem.split("_")[0])
        episode = data.get("episode_title", "")
        published = data.get("published", "")
        episode_url = data.get("episode_url", "")

        # Extract claims that need verification
        claims = data.get("claims_to_note", [])
        for claim in claims:
            if isinstance(claim, str) and len(claim) > 20:
                candidates.append({
                    "raw_text": claim,
                    "source_type": "podcast_claim",
                    "source": f"{podcast}: {episode}",
                    "source_url": episode_url,
                    "date": published,
                })

        # Extract science topics as potential question seeds
        topics = data.get("science_topics", [])
        for topic in topics:
            if isinstance(topic, str) and len(topic) > 15:
                candidates.append({
                    "raw_text": topic,
                    "source_type": "podcast_topic",
                    "source": f"{podcast}: {episode}",
                    "source_url": episode_url,
                    "date": published,
                })

    return candidates


def _mine_trending_topics():
    """Extract trending/spiking topics from STM topic history."""
    if not TOPIC_HISTORY.exists():
        return []

    try:
        raw = json.loads(TOPIC_HISTORY.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    candidates = []

    # Handle {"runs": [...]} structure
    if isinstance(raw, dict):
        history = raw.get("runs", [])
    elif isinstance(raw, list):
        history = raw
    else:
        return []

    # Get recent snapshots
    recent = history[-5:]

    for snapshot in recent:
        timestamp = snapshot.get("timestamp", "")
        topics = snapshot.get("topics", [])
        for topic in topics:
            name = topic.get("name", "")
            source_count = topic.get("source_count", 0)
            if name and source_count >= 3:
                # Use article headlines if available (much more specific than topic name)
                top_articles = topic.get("top_articles", [])
                if top_articles:
                    for article in top_articles:
                        title = article.get("title", "")
                        link = article.get("link", "")
                        outlet = article.get("source", "")
                        if title:
                            candidates.append({
                                "raw_text": f"{name}: {title}",
                                "source_type": "trending_article",
                                "source": f"STM — {outlet}" if outlet else f"STM ({source_count} sources)",
                                "source_url": link or "https://scifi-signals.github.io/Science-Trend-Monitor-Agent/",
                                "date": timestamp[:10] if timestamp else "",
                                "momentum": source_count,
                            })
                else:
                    # Fallback: topic name only (old format)
                    candidates.append({
                        "raw_text": name,
                        "source_type": "trending_topic",
                        "source": f"STM ({source_count} sources)",
                        "source_url": "https://scifi-signals.github.io/Science-Trend-Monitor-Agent/",
                        "date": timestamp[:10] if timestamp else "",
                        "momentum": source_count,
                    })

    # Deduplicate by topic name
    seen = set()
    unique = []
    for c in candidates:
        key = c["raw_text"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def _rank_and_refine(raw_questions, max_questions):
    """Use Claude to rank candidates and convert to BoS-style questions."""
    # Format candidates for Claude
    candidates_text = ""
    for i, q in enumerate(raw_questions[:120]):  # Cap at 120 candidates
        candidates_text += f"{i+1}. [{q['source_type']}] {q['raw_text']}\n"
        candidates_text += f"   Source: {q['source']}\n"

    prompt = f"""I have {len(raw_questions)} candidate topics/claims from science podcasts and news trends.
Convert the best ones into "Based on Science" article questions.

The "Based on Science" series exists to COMBAT MISINFORMATION — to provide authoritative,
evidence-based answers where the public commonly believes something WRONG or is confused
by conflicting claims. The goal is to CORRECT MISCONCEPTIONS, not just inform.

Candidates:
{candidates_text}

Select the top {max_questions} candidates that would make the best "Based on Science" articles.

REQUIRED criteria — every question MUST have ALL of these:
1. ACTIVE MISINFORMATION: There must be a specific, identifiable wrong belief, myth, or
   dangerous confusion circulating among the public (on social media, in news, in common
   assumptions). If you cannot name the specific wrong belief, REJECT the topic.
2. AUTHORITATIVE EVIDENCE: Strong scientific evidence exists from NASEM, IPCC, CDC, WHO,
   or peer-reviewed meta-analyses that directly contradicts or clarifies the misconception.
3. PUBLIC STAKES: Real health, safety, or environmental consequences if people continue
   believing the wrong thing.
4. ACCESSIBILITY: Can be answered at an 8th-grade reading level for a general audience.

REJECT topics that are:
- Purely informational with no wrong belief to correct (e.g., "How fast are MRI scans?")
- Speculative or cutting-edge science without established consensus
- Already well-covered by simple Google searches or existing fact-checks
- Policy/opinion questions rather than evidence questions

Return a JSON array:
```json
[
  {{
    "question": "Does [topic] cause [effect]?",
    "misinformation_narrative": "The specific wrong belief (e.g., 'Many people believe X when in fact Y')",
    "public_stakes": "What happens if people keep believing the wrong thing",
    "rationale": "Why this is a good BoS question — what misconception does it correct?",
    "source_indices": [1, 5, 12, 34, 47],
    "estimated_sources": "What types of authoritative sources likely exist",
    "priority": "high|medium|low",
    "tags": ["Health and Medicine", "Public Health"]
  }}
]
```

IMPORTANT: For source_indices, include ALL candidate numbers that relate to the question —
every podcast claim, topic, or trending signal that supports or relates to this question.
More source indices = stronger provenance. A question backed by 5+ independent signals
is much stronger than one backed by 1.

Return ONLY the JSON array. Do NOT include questions where you cannot identify a specific,
real misinformation narrative. It is better to return fewer high-quality questions than to
pad the list with informational topics."""

    system = "You are an editorial strategist for the National Academies' 'Based on Science' series. Your mission is to identify science topics where PUBLIC MISINFORMATION is actively causing harm and where authoritative evidence can correct the record. You only select questions that combat specific, identifiable wrong beliefs."

    response = ask_claude(prompt, system_prompt=system)

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        ranked = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        print(f"  Failed to parse ranking response")
        ranked = []

    # Enrich with source info
    for item in ranked:
        indices = item.get("source_indices", [])
        item["raw_sources"] = [
            raw_questions[i-1] for i in indices
            if 0 < i <= len(raw_questions)
        ]

    return ranked


def print_discoveries(questions):
    """Pretty-print discovered questions."""
    if not questions:
        print("\nNo questions discovered.")
        return

    print(f"\n{'='*60}")
    print(f"DISCOVERED BoS QUESTIONS ({len(questions)})")
    print(f"{'='*60}")

    for i, q in enumerate(questions, 1):
        priority = q.get("priority", "?")
        priority_color = {"high": "***", "medium": "**", "low": "*"}.get(priority, "")
        print(f"\n{i}. {priority_color}{q.get('question', '?')}{priority_color}")
        print(f"   Priority: {priority}")
        print(f"   Rationale: {q.get('rationale', '')}")
        print(f"   Sources: {q.get('estimated_sources', '')}")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    questions = discover_questions()
    print_discoveries(questions)
