"""Generate BoS-style articles from evidence and consensus."""

import json

from llm import ask_claude
from prompts.article_generation import ARTICLE_GENERATION_PROMPT
from config import OUTPUT_DIR


def generate_article(consensus, evidence_package):
    """Generate a Based on Science article from consensus and evidence."""
    question = consensus["question"]
    question_id = consensus.get("question_id", evidence_package.get("question_id", "unknown"))

    # Build evidence summary — include findings but trim raw text for token economy
    evidence_for_prompt = []
    for src in evidence_package["evidence"]:
        if src.get("error") or not src.get("findings"):
            continue
        evidence_for_prompt.append({
            "source": src["source"],
            "url": src.get("url", ""),
            "tier": src.get("tier", 3),
            "findings": src.get("findings", []),
        })

    prompt = f"""Generate a "Based on Science" article for the following question.

Question: {question}

Consensus Analysis:
{json.dumps(consensus, indent=2)}

Full Evidence Package ({len(evidence_for_prompt)} sources):
{json.dumps(evidence_for_prompt, indent=2)}

Write the complete article in Markdown format following the BoS style guide exactly."""

    print("  Generating article...")
    article = ask_claude(prompt, system_prompt=ARTICLE_GENERATION_PROMPT, max_tokens=8192)

    # Validate structure
    validation = _validate_article(article)
    if validation["issues"]:
        print(f"  Validation issues: {validation['issues']}")
    else:
        print("  Article structure validated OK")

    result = {
        "question": question,
        "question_id": question_id,
        "article_markdown": article,
        "validation": validation,
    }

    # Save article
    out_path = OUTPUT_DIR / "articles" / f"{question_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(article, encoding="utf-8")
    print(f"  Article saved to {out_path}")

    return result


def _validate_article(article):
    """Check that article has all required BoS sections."""
    required_sections = [
        "The Short Answer",
        "Some People Face Greater Risks",
        "What You Can Do",
        "Additional Resources",
    ]
    issues = []
    article_lower = article.lower()

    for section in required_sections:
        if section.lower() not in article_lower:
            issues.append(f"Missing required section: {section}")

    if "based on science" not in article_lower:
        issues.append("Missing 'Based on Science' subtitle")

    if "---" not in article:
        issues.append("Missing horizontal rules between sections")

    # Check for tag line at end
    if "tags:" not in article_lower:
        issues.append("Missing Tags line at end")

    # Check for source links in body (not just Additional Resources)
    import re
    link_count = len(re.findall(r'\[[^\]]+\]\(https?://[^)]+\)', article))
    if link_count < 3:
        issues.append(f"Only {link_count} source links found — articles should link to sources inline")

    return {"valid": len(issues) == 0, "issues": issues}


def load_article(question_id):
    """Load saved article markdown from disk."""
    path = OUTPUT_DIR / "articles" / f"{question_id}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
