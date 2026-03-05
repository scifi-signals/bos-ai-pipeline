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
    raw_questions.extend(podcast_qs)
    print(f"  Podcast claims: {len(podcast_qs)} candidates")

    # Source 2: STM trending topics
    trending_qs = _mine_trending_topics()
    raw_questions.extend(trending_qs)
    print(f"  Trending topics: {len(trending_qs)} candidates")

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

        # Extract claims that need verification
        claims = data.get("claims_to_note", [])
        for claim in claims:
            if isinstance(claim, str) and len(claim) > 20:
                candidates.append({
                    "raw_text": claim,
                    "source_type": "podcast_claim",
                    "source": f"{podcast}: {episode}",
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
                candidates.append({
                    "raw_text": name,
                    "source_type": "trending_topic",
                    "source": f"STM ({source_count} sources)",
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
    for i, q in enumerate(raw_questions[:60]):  # Cap at 60 to avoid token overflow
        candidates_text += f"{i+1}. [{q['source_type']}] {q['raw_text']}\n"
        candidates_text += f"   Source: {q['source']}\n"

    prompt = f"""I have {len(raw_questions)} candidate topics/claims from science podcasts and news trends.
Convert the best ones into "Based on Science" article questions.

Candidates:
{candidates_text}

Select the top {max_questions} candidates that would make the best "Based on Science" articles.

Criteria for good BoS questions:
- Questions the general public would actually ask (not specialist jargon)
- Have strong scientific evidence available (not speculative/cutting-edge)
- Health, environment, or daily-life relevance
- Can be answered at 8th-grade reading level
- Not already well-covered by simple Google searches

Return a JSON array:
```json
[
  {{
    "question": "Does [topic] cause [effect]?",
    "rationale": "Why this is a good BoS question",
    "source_indices": [1, 5, 12],
    "estimated_sources": "What types of authoritative sources likely exist",
    "priority": "high|medium|low"
  }}
]
```

Return ONLY the JSON array."""

    system = "You are an editorial strategist for the National Academies' 'Based on Science' series. You identify science questions the public is actively asking that can be answered with authoritative evidence."

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
