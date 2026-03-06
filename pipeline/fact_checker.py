"""Independent fact-checking via GPT-4o + reading level analysis."""

import json
import re

from llm import ask_gpt4o
from prompts.fact_checking import FACT_CHECK_PROMPT
from config import OUTPUT_DIR, OPENAI_API_KEY


def fact_check(article_markdown, evidence_package):
    """Fact-check an article against its evidence package. Returns detailed report."""
    question_id = evidence_package.get("question_id", "unknown")

    # Build compact evidence for GPT-4o (trim to essentials)
    evidence_compact = []
    for src in evidence_package["evidence"]:
        if src.get("error") or not src.get("findings"):
            continue
        evidence_compact.append({
            "source": src["source"],
            "tier": src.get("tier", 3),
            "findings": src.get("findings", []),
        })

    prompt = f"""Article to fact-check:
---
{article_markdown}
---

Evidence package ({len(evidence_compact)} sources):
{json.dumps(evidence_compact, indent=2)}

Check every factual claim in the article against the evidence. Return JSON."""

    # Use GPT-4o for independent verification (different model prevents self-confirmation)
    if not OPENAI_API_KEY:
        raise RuntimeError("Fact-check requires OPENAI_API_KEY — dual-model verification "
                           "needs GPT-4o, not Claude checking its own work")
    print("  Running fact-check (GPT-4o)...")
    response = ask_gpt4o(prompt, system_prompt=FACT_CHECK_PROMPT, max_tokens=4096)

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        result = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        result = {"error": "Failed to parse fact-check response", "raw": response[:1000]}

    # Reading level check
    print("  Checking reading level...")
    reading_level = check_reading_level(article_markdown)
    result["reading_level"] = reading_level

    # Print summary
    summary = result.get("summary", {})
    print(f"  Fact-check: {summary.get('confirmed', '?')} confirmed, "
          f"{summary.get('plausible', '?')} plausible, "
          f"{summary.get('unsupported', '?')} unsupported, "
          f"{summary.get('contradicted', '?')} contradicted")
    print(f"  Reading level: FK grade {reading_level.get('flesch_kincaid_grade', '?')} "
          f"({'PASS' if reading_level.get('target_met') else 'FAIL'})")
    print(f"  Overall: {result.get('overall_assessment', '?')}")

    # Save report
    out_path = OUTPUT_DIR / "evidence" / f"{question_id}_factcheck.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Fact-check saved to {out_path}")

    return result


def check_reading_level(text):
    """Check reading level using textstat. Target: Flesch-Kincaid grade <= 8.0."""
    import textstat

    # Strip markdown formatting for accurate measurement
    clean = re.sub(r'#{1,6}\s*', '', text)                    # headings
    clean = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', clean)   # bold/italic
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)    # links
    clean = re.sub(r'---+', '', clean)                         # horizontal rules
    clean = re.sub(r'^\s*[-*]\s+', '', clean, flags=re.MULTILINE)  # list markers
    clean = re.sub(r'\n{2,}', '\n', clean).strip()

    fk_grade = textstat.flesch_kincaid_grade(clean)
    return {
        "flesch_kincaid_grade": round(fk_grade, 1),
        "flesch_reading_ease": round(textstat.flesch_reading_ease(clean), 1),
        "gunning_fog": round(textstat.gunning_fog(clean), 1),
        "automated_readability_index": round(textstat.automated_readability_index(clean), 1),
        "target_met": fk_grade <= 8.0,
    }
