"""Discovery orchestrator — find questions, score NASEM sources, write queue.

Runs question_discoverer + nasem_sourcer for each question, writes:
  - pipeline/questions/{id}.json for new questions (so generate workflow can consume)
  - discovered_questions.json at repo root (landing page reads this)
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import QUESTIONS_DIR, OUTPUT_DIR

ROOT = Path(__file__).resolve().parent.parent  # repo root


def slugify(question):
    """Generate a stable question_id from question text.

    Takes the first 4-5 meaningful words, lowercased, underscored.
    e.g. "How effective are pharmacists at providing vaccinations compared to doctors?"
         → "pharmacists_providing_vaccinations_compared_doctors"
    """
    stop_words = {
        "does", "do", "is", "are", "can", "will", "how", "what", "why", "when",
        "the", "a", "an", "of", "in", "to", "for", "and", "or", "not", "with",
        "from", "by", "on", "at", "it", "its", "this", "that", "be", "have",
        "has", "had", "there", "about", "more", "than", "their", "your", "our",
        "which", "who", "whom", "much", "many",
    }
    words = re.findall(r'[a-z]+', question.lower())
    meaningful = [w for w in words if w not in stop_words and len(w) > 2]
    slug = "_".join(meaningful[:5])
    return slug or "unknown_question"


def run_discovery(max_questions=15):
    """Full discovery pipeline: find questions, score NASEM sources, write outputs."""
    print("=" * 60)
    print("BoS Discovery Pipeline")
    print("=" * 60)

    # Step 1: Discover questions
    print("\n[1/4] Discovering questions from STM + podcasts...")
    from question_discoverer import discover_questions
    questions = discover_questions(max_questions=max_questions)
    if not questions:
        print("  No questions discovered. Exiting.")
        return

    print(f"  Found {len(questions)} questions")

    # Step 2: Generate IDs and deduplicate against existing configs
    print("\n[2/4] Generating IDs and checking for duplicates...")
    existing_configs = {p.stem for p in QUESTIONS_DIR.glob("*.json")}
    new_questions = []
    for q in questions:
        qid = slugify(q["question"])
        q["id"] = qid
        if qid in existing_configs:
            print(f"  SKIP (exists): {qid}")
        else:
            new_questions.append(q)
            print(f"  NEW: {qid}")

    # Step 3: Find NASEM sources for each question
    print(f"\n[3/4] Finding NASEM sources for {len(questions)} questions...")
    from nasem_sourcer import find_nasem_sources
    for q in questions:
        print(f"\n  Sourcing: {q['question'][:60]}...")
        try:
            sources = find_nasem_sources(q["question"], max_results=10, use_llm_rerank=False)
            q["nasem_source_count"] = len(sources)
            q["nasem_sources_preview"] = [
                f"{s['name']} ({s.get('year', '?')})" for s in sources[:5]
            ]
            q["nasem_sources_full"] = sources
        except Exception as e:
            print(f"    ERROR: {e}")
            q["nasem_source_count"] = 0
            q["nasem_sources_preview"] = []
            q["nasem_sources_full"] = []

    # Step 4a: Write question configs for new questions
    print(f"\n[4/4] Writing outputs...")
    QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    for q in new_questions:
        config = {
            "id": q["id"],
            "question": q["question"],
            "topic": q.get("rationale", "")[:100],
            "tags": q.get("tags", _infer_tags(q)),
            "sources": [
                {
                    "name": s["name"],
                    "url": s["url"],
                    "type": s.get("type", "web"),
                    "tier": s.get("tier", 1),
                }
                for s in q.get("nasem_sources_full", [])[:8]
            ],
        }
        config_path = QUESTIONS_DIR / f"{q['id']}.json"
        config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Config: pipeline/questions/{q['id']}.json")

    # Step 4b: Build discovered_questions.json
    _write_discovery_queue(questions)
    print("\nDiscovery complete.")


def _infer_tags(question_data):
    """Infer topic tags from question text and rationale."""
    text = (question_data.get("question", "") + " " +
            question_data.get("rationale", "")).lower()
    tags = []
    tag_signals = {
        "Health and Medicine": ["health", "disease", "medical", "drug", "vaccine",
                                "cancer", "heart", "lung", "breathing", "mental"],
        "Climate Change": ["climate", "warming", "carbon", "greenhouse", "temperature"],
        "Environment": ["pollution", "air quality", "water", "wildfire", "ozone",
                        "biodiversity", "ecosystem"],
        "Public Health": ["public health", "pandemic", "epidemic", "cdc", "who",
                          "vaccination", "pharmacist"],
        "Energy": ["energy", "solar", "wind", "nuclear", "fossil", "renewable",
                    "battery", "electric"],
        "Nutrition": ["nutrition", "diet", "food", "obesity", "fasting"],
        "Technology": ["ai", "artificial intelligence", "machine learning", "crispr",
                       "gene editing", "technology"],
    }
    for tag, signals in tag_signals.items():
        if any(s in text for s in signals):
            tags.append(tag)
    return tags[:3] if tags else ["Science"]


def _write_discovery_queue(questions):
    """Write discovered_questions.json, merging with article manifest for status."""
    # Load article manifest to identify published articles
    manifest_path = ROOT / "article_manifest.json"
    published_ids = set()
    published_data = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for article in manifest.get("articles", []):
            aid = article.get("id", "")
            published_ids.add(aid)
            published_data[aid] = article

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entries = []
    for q in questions:
        qid = q["id"]
        is_published = qid in published_ids

        entry = {
            "id": qid,
            "question": q["question"],
            "priority": q.get("priority", "medium"),
            "rationale": q.get("rationale", ""),
            "tags": q.get("tags", _infer_tags(q)),
            "nasem_source_count": q.get("nasem_source_count", 0),
            "nasem_sources_preview": q.get("nasem_sources_preview", []),
            "discovered_at": today,
            "status": "published" if is_published else "pending",
        }
        if is_published:
            pub = published_data[qid]
            entry["article_url"] = pub.get("article_url", "")
            entry["evidence_url"] = pub.get("evidence_url", "")
        entries.append(entry)

    # Also include published articles not in discovery results
    discovered_ids = {q["id"] for q in questions}
    for aid, article in published_data.items():
        if aid not in discovered_ids:
            entries.append({
                "id": aid,
                "question": article.get("title", ""),
                "priority": "n/a",
                "rationale": "",
                "tags": article.get("tags", []),
                "nasem_source_count": article.get("sources_count", 0),
                "nasem_sources_preview": [],
                "discovered_at": "",
                "status": "published",
                "article_url": article.get("article_url", ""),
                "evidence_url": article.get("evidence_url", ""),
            })

    # Sort: pending (high → medium → low) first, then published
    priority_order = {"high": 0, "medium": 1, "low": 2, "n/a": 3}
    entries.sort(key=lambda e: (
        0 if e["status"] == "pending" else 1,
        priority_order.get(e["priority"], 2),
    ))

    output = {
        "generated_at": now,
        "questions": entries,
    }

    out_path = ROOT / "discovered_questions.json"
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Queue: discovered_questions.json ({len(entries)} questions)")


if __name__ == "__main__":
    count = 15
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            pass
    run_discovery(max_questions=count)
