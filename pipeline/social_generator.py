"""Generate social media posts from article content and evidence."""

import json
from pathlib import Path

from config import OUTPUT_DIR
from llm import ask_claude
from prompts.social_generation import SOCIAL_GENERATION_PROMPT


def generate_social_posts(article_markdown, evidence_package, question_id):
    """Generate short-form and long-form social posts for an article.

    Args:
        article_markdown: Full article text in markdown
        evidence_package: Evidence dict with findings and sources
        question_id: Used for output filename

    Returns:
        Dict with short_post, long_post, hashtags or None on failure
    """
    print("  Generating social posts...")

    # Build evidence summary for the prompt
    evidence_summary = _build_evidence_summary(evidence_package)

    prompt = SOCIAL_GENERATION_PROMPT.format(
        article_markdown=article_markdown[:4000],  # Cap to avoid token overflow
        evidence_summary=evidence_summary,
    )

    system = ("You are a science communications specialist for the National Academies. "
              "You write factual, accessible social media posts that cite sources.")

    response = ask_claude(prompt, system_prompt=system, max_tokens=1024)

    # Parse JSON response
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        result = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError) as e:
        print(f"  Failed to parse social posts: {e}")
        return None

    # Validate required fields
    if "short_post" not in result or "long_post" not in result:
        print("  Social post response missing required fields")
        return None

    # Add metadata
    result["question_id"] = question_id
    if "hashtags" not in result:
        result["hashtags"] = ["#BasedOnScience"]

    # Save output
    social_dir = OUTPUT_DIR / "social"
    social_dir.mkdir(parents=True, exist_ok=True)
    out_path = social_dir / f"{question_id}.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Social posts saved to {out_path}")
    return result


def _build_evidence_summary(evidence_package):
    """Extract key findings for the social generation prompt."""
    lines = []
    question = evidence_package.get("question", "")
    lines.append(f"Question: {question}")
    lines.append(f"Sources: {evidence_package.get('sources_processed', 0)}")
    lines.append(f"Total findings: {evidence_package.get('total_findings', 0)}")
    lines.append("")

    # Pull top findings from each source (max 3 per source, 5 sources)
    for src in evidence_package.get("evidence", [])[:5]:
        if src.get("error"):
            continue
        source_name = src.get("source", "Unknown")
        for finding in src.get("findings", [])[:3]:
            claim = finding.get("claim", "")
            data = finding.get("data_points", [])
            data_str = "; ".join(data[:2]) if data else ""
            line = f"- {claim}"
            if data_str:
                line += f" ({data_str})"
            line += f" [Source: {source_name}]"
            lines.append(line)

    return "\n".join(lines[:30])  # Cap at 30 lines
