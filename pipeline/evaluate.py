"""Compare generated articles against published reference articles."""

import json
import re
from pathlib import Path

from config import OUTPUT_DIR, REFERENCE_DIR
from fact_checker import check_reading_level


def evaluate(question_id, reference_path=None):
    """Compare generated article to reference article."""
    # Load generated article
    gen_path = OUTPUT_DIR / "articles" / f"{question_id}.md"
    if not gen_path.exists():
        print(f"  No generated article found at {gen_path}")
        return None
    generated = gen_path.read_text(encoding="utf-8")

    # Load reference article
    if reference_path:
        ref_path = Path(reference_path)
    else:
        ref_path = REFERENCE_DIR / f"{question_id}.md"
    if not ref_path.exists():
        print(f"  No reference article found at {ref_path}")
        return None
    reference = ref_path.read_text(encoding="utf-8")

    print(f"  Comparing generated ({len(generated)} chars) vs reference ({len(reference)} chars)")

    # Structure comparison
    gen_sections = _extract_sections(generated)
    ref_sections = _extract_sections(reference)
    structure = _compare_structure(gen_sections, ref_sections)

    # Reading level comparison
    gen_rl = check_reading_level(generated)
    ref_rl = check_reading_level(reference)

    # Data point coverage
    gen_datapoints = _extract_data_points(generated)
    ref_datapoints = _extract_data_points(reference)
    coverage = _compare_data_points(gen_datapoints, ref_datapoints)

    # Topic coverage
    gen_topics = _extract_topics(generated)
    ref_topics = _extract_topics(reference)
    topic_coverage = _compare_topics(gen_topics, ref_topics)

    result = {
        "question_id": question_id,
        "generated_length": len(generated),
        "reference_length": len(reference),
        "structure": structure,
        "reading_level": {
            "generated": gen_rl,
            "reference": ref_rl,
            "grade_diff": round(gen_rl["flesch_kincaid_grade"] - ref_rl["flesch_kincaid_grade"], 1),
        },
        "data_point_coverage": coverage,
        "topic_coverage": topic_coverage,
    }

    # Print report
    _print_report(result)

    # Save
    out_path = OUTPUT_DIR / "evidence" / f"{question_id}_evaluation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Evaluation saved to {out_path}")

    return result


def _extract_sections(markdown):
    """Extract H2 section names from markdown."""
    return [m.group(1) for m in re.finditer(r'^## (.+)$', markdown, re.MULTILINE)]


def _compare_structure(gen_sections, ref_sections):
    """Compare section structure between generated and reference."""
    ref_set = set(s.lower() for s in ref_sections)
    gen_set = set(s.lower() for s in gen_sections)

    return {
        "generated_sections": gen_sections,
        "reference_sections": ref_sections,
        "matching": sorted(gen_set & ref_set),
        "in_generated_only": sorted(gen_set - ref_set),
        "in_reference_only": sorted(ref_set - gen_set),
        "match_ratio": round(len(gen_set & ref_set) / max(len(ref_set), 1), 2),
    }


def _extract_data_points(text):
    """Extract numeric data points from text."""
    patterns = [
        r'\d[\d,]+\s*(?:deaths|people|million|billion)',
        r'\d+[\d,]*\s*(?:percent|%)',
        r'\d{4}\s*(?:report|study|assessment)',
        r'(?:roughly|approximately|about|estimated|an estimated)\s+[\d,]+',
    ]
    points = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            points.append(m.group(0).strip())
    return points


def _compare_data_points(gen_points, ref_points):
    """Compare data point coverage."""
    # Normalize for comparison
    def normalize(s):
        return re.sub(r'[,\s]+', '', s.lower())

    gen_norm = {normalize(p): p for p in gen_points}
    ref_norm = {normalize(p): p for p in ref_points}

    matched = []
    for rn, rp in ref_norm.items():
        for gn, gp in gen_norm.items():
            if rn in gn or gn in rn:
                matched.append({"reference": rp, "generated": gp})
                break

    return {
        "reference_data_points": ref_points,
        "generated_data_points": gen_points,
        "matched_count": len(matched),
        "reference_count": len(ref_points),
        "coverage_ratio": round(len(matched) / max(len(ref_points), 1), 2),
        "matched": matched,
    }


def _extract_topics(text):
    """Extract key topics discussed in the text."""
    keywords = [
        "ozone", "smog", "wildfire", "dust", "pollen", "allergy", "asthma",
        "copd", "particulate", "air quality", "ragweed", "camp fire",
        "ground-level ozone", "carbon dioxide", "drought",
    ]
    found = []
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower:
            found.append(kw)
    return found


def _compare_topics(gen_topics, ref_topics):
    """Compare topic coverage."""
    gen_set = set(gen_topics)
    ref_set = set(ref_topics)
    return {
        "reference_topics": sorted(ref_set),
        "generated_topics": sorted(gen_set),
        "covered": sorted(gen_set & ref_set),
        "missing": sorted(ref_set - gen_set),
        "additional": sorted(gen_set - ref_set),
        "coverage_ratio": round(len(gen_set & ref_set) / max(len(ref_set), 1), 2),
    }


def _print_report(result):
    """Print a human-readable evaluation report."""
    print("\n" + "=" * 60)
    print("EVALUATION REPORT")
    print("=" * 60)

    # Structure
    s = result["structure"]
    print(f"\nStructure: {s['match_ratio']:.0%} section match")
    if s["in_reference_only"]:
        print(f"  Missing sections: {', '.join(s['in_reference_only'])}")
    if s["in_generated_only"]:
        print(f"  Extra sections: {', '.join(s['in_generated_only'])}")

    # Reading level
    rl = result["reading_level"]
    gen_fk = rl["generated"]["flesch_kincaid_grade"]
    ref_fk = rl["reference"]["flesch_kincaid_grade"]
    print(f"\nReading Level: Generated FK {gen_fk} vs Reference FK {ref_fk} (diff: {rl['grade_diff']:+.1f})")
    print(f"  Generated target met: {'YES' if rl['generated']['target_met'] else 'NO'}")
    print(f"  Reference target met: {'YES' if rl['reference']['target_met'] else 'NO'}")

    # Data points
    dp = result["data_point_coverage"]
    print(f"\nData Points: {dp['matched_count']}/{dp['reference_count']} reference points covered ({dp['coverage_ratio']:.0%})")

    # Topics
    tc = result["topic_coverage"]
    print(f"\nTopics: {tc['coverage_ratio']:.0%} coverage")
    if tc["missing"]:
        print(f"  Missing: {', '.join(tc['missing'])}")
    if tc["additional"]:
        print(f"  Additional: {', '.join(tc['additional'])}")

    print("\n" + "=" * 60)
