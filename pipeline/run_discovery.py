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
    print("\n[1/5] Discovering questions from STM + podcasts...")
    from question_discoverer import discover_questions
    questions = discover_questions(max_questions=max_questions)
    if not questions:
        print("  No questions discovered. Exiting.")
        return

    print(f"  Found {len(questions)} questions")

    # Step 2: Verify misinformation narratives are real (not hallucinated)
    print(f"\n[2/5] Verifying misinformation narratives...")
    questions = _verify_narratives(questions)
    verified_count = sum(1 for q in questions if q.get("verification_status") == "verified")
    flagged_count = sum(1 for q in questions if q.get("verification_status") == "needs_review")
    print(f"  Verified: {verified_count}, Needs review: {flagged_count}")

    # Step 3: Generate IDs and deduplicate
    print("\n[3/5] Generating IDs and deduplicating...")
    existing_configs = {p.stem for p in QUESTIONS_DIR.glob("*.json")}

    # Load existing question texts for semantic dedup
    existing_questions = []
    for p in QUESTIONS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            existing_questions.append(data.get("question", ""))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    new_questions = []
    batch_questions = []  # Track questions within this batch too
    for q in questions:
        qid = slugify(q["question"])
        q["id"] = qid

        # Exact slug match
        if qid in existing_configs:
            print(f"  SKIP (exists): {qid}")
            continue

        # Semantic similarity check against existing + batch
        similar = _find_similar(q["question"], existing_questions + batch_questions,
                                threshold=0.65)
        if similar:
            print(f"  SKIP (similar to '{similar[:50]}...'): {qid}")
            continue

        new_questions.append(q)
        batch_questions.append(q["question"])
        print(f"  NEW: {qid}")

    # Step 4: Find NASEM sources for each question
    print(f"\n[4/5] Finding NASEM sources for {len(questions)} questions...")
    from nasem_sourcer import find_nasem_sources
    for q in questions:
        print(f"\n  Sourcing: {q['question'][:60]}...")
        try:
            sources = find_nasem_sources(q["question"], max_results=10, use_llm_rerank=True)
            q["nasem_source_count"] = len(sources)
            q["nasem_sources_preview"] = [
                {"name": f"{s['name']} ({s.get('year', '?')})", "url": s.get("url", "")}
                for s in sources
            ]
            q["nasem_sources_full"] = sources
        except Exception as e:
            print(f"    ERROR: {e}")
            q["nasem_source_count"] = 0
            q["nasem_sources_preview"] = []
            q["nasem_sources_full"] = []

    # Step 5a: Write question configs for new questions
    print(f"\n[5/5] Writing outputs...")
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
            "discovery_sources": [
                {
                    "type": rs.get("source_type", ""),
                    "text": rs.get("raw_text", ""),
                    "origin": rs.get("source", ""),
                    "date": rs.get("date", ""),
                }
                for rs in q.get("raw_sources", [])
            ],
        }
        config_path = QUESTIONS_DIR / f"{q['id']}.json"
        config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Config: pipeline/questions/{q['id']}.json")

    # Step 5b: Build discovered_questions.json
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


def _find_similar(question, existing_questions, threshold=0.65):
    """Check if question is semantically similar to any existing question.

    Uses word-set Jaccard similarity on meaningful words. Returns the similar
    question text if found, or None.

    Threshold 0.65 catches near-duplicates like:
      "How effective are pharmacists at providing vaccinations?"
      "How effective are pharmacists at providing healthcare?"
    while allowing genuinely different questions through.
    """
    stop_words = {
        "does", "do", "is", "are", "can", "will", "how", "what", "why", "when",
        "the", "a", "an", "of", "in", "to", "for", "and", "or", "not", "with",
        "from", "by", "on", "at", "it", "its", "this", "that", "be", "have",
        "has", "had", "there", "about", "more", "than",
    }

    def meaningful_words(text):
        words = set(re.findall(r'[a-z]+', text.lower()))
        return words - stop_words

    q_words = meaningful_words(question)
    if not q_words:
        return None

    for existing in existing_questions:
        if not existing:
            continue
        e_words = meaningful_words(existing)
        if not e_words:
            continue
        # Jaccard similarity
        intersection = len(q_words & e_words)
        union = len(q_words | e_words)
        if union > 0 and intersection / union >= threshold:
            return existing

    return None


def _verify_narratives(questions):
    """Skeptical verification: check if misinformation narratives are real.

    Uses a second LLM call to catch cases where the ranking step hallucinated
    a misinformation narrative that doesn't actually exist in public discourse.
    Questions with implausible narratives get status 'needs_review'.
    """
    from llm import ask_claude

    # Build batch of narratives to verify
    narratives = []
    for i, q in enumerate(questions):
        narrative = q.get("misinformation_narrative", "")
        if narrative:
            narratives.append(f"{i+1}. Question: {q['question']}\n   Claimed misinformation: {narrative}")

    if not narratives:
        for q in questions:
            q["verification_status"] = "no_narrative"
        return questions

    prompt = f"""You are a skeptical fact-checker. For each claimed misinformation narrative below,
determine if this is a REAL, currently circulating public misconception — or if it was
likely invented/exaggerated by the AI that generated it.

A narrative is REAL if:
- You can identify specific communities, platforms, or media where this belief circulates
- It reflects a genuine public confusion (not just an academic disagreement)
- People actually hold this wrong belief in meaningful numbers

A narrative is SUSPECT if:
- It sounds plausible but you can't point to where people actually believe this
- It's a straw man — nobody really argues this position
- It confuses "people don't know X" with "people believe the opposite of X"
- It's an obscure academic nuance dressed up as public misinformation

{chr(10).join(narratives)}

For each numbered item, respond with ONLY:
- The number, then REAL or SUSPECT, then a brief reason (1 sentence)

Example:
1. REAL — Anti-vax communities on Facebook actively claim vaccines cause autism.
2. SUSPECT — No significant public group believes MRI scans are getting slower.

Respond for all {len(narratives)} items:"""

    try:
        response = ask_claude(prompt, max_tokens=1000)
        # Parse responses
        verdicts = {}
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            match = re.match(r'(\d+)\.\s*(REAL|SUSPECT)', line, re.IGNORECASE)
            if match:
                idx = int(match.group(1)) - 1
                verdict = match.group(2).upper()
                verdicts[idx] = verdict

        for i, q in enumerate(questions):
            if i in verdicts:
                if verdicts[i] == "REAL":
                    q["verification_status"] = "verified"
                else:
                    q["verification_status"] = "needs_review"
                    q["priority"] = "low"  # Demote suspect narratives
                    print(f"    SUSPECT: {q['question'][:60]}...")
            else:
                q["verification_status"] = "unverified"

    except Exception as e:
        print(f"  Verification failed ({e}), marking all as unverified")
        for q in questions:
            q["verification_status"] = "unverified"

    return questions


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
            "misinformation_narrative": q.get("misinformation_narrative", ""),
            "public_stakes": q.get("public_stakes", ""),
            "verification_status": q.get("verification_status", ""),
            "tags": q.get("tags", _infer_tags(q)),
            "nasem_source_count": q.get("nasem_source_count", 0),
            "nasem_sources_preview": q.get("nasem_sources_preview", []),
            "discovery_sources": [
                {
                    "type": rs.get("source_type", rs.get("type", "")),
                    "text": rs.get("raw_text", rs.get("text", "")),
                    "origin": rs.get("source", rs.get("origin", "")),
                    "date": rs.get("date", ""),
                }
                for rs in q.get("raw_sources", q.get("discovery_sources", []))
            ],
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
