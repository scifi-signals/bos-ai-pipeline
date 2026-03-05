"""Cross-source consensus analysis via Claude."""

import json

from llm import ask_claude
from prompts.consensus_analysis import CONSENSUS_ANALYSIS_PROMPT
from config import OUTPUT_DIR


def build_consensus(evidence_package):
    """Analyze cross-source consensus from an evidence package."""
    question = evidence_package["question"]
    question_id = evidence_package["question_id"]

    # Format evidence for Claude — skip sources with errors
    evidence_summary = []
    for src in evidence_package["evidence"]:
        if src.get("error") or not src.get("findings"):
            continue
        evidence_summary.append({
            "source": src["source"],
            "tier": src.get("tier", 3),
            "url": src.get("url", ""),
            "findings": src.get("findings", []),
        })

    if not evidence_summary:
        return {"error": "No valid evidence to analyze", "question": question}

    prompt = f"""Question: {question}

Evidence from {len(evidence_summary)} sources:
{json.dumps(evidence_summary, indent=2)}

Analyze the cross-source consensus. Return JSON."""

    print(f"  Building consensus from {len(evidence_summary)} sources...")
    response = ask_claude(prompt, system_prompt=CONSENSUS_ANALYSIS_PROMPT, max_tokens=8192)

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        consensus = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        consensus = {"error": "Failed to parse consensus", "raw": response[:1000]}

    consensus["question"] = question
    consensus["question_id"] = question_id
    consensus["sources_analyzed"] = len(evidence_summary)

    # Save consensus
    out_path = OUTPUT_DIR / "evidence" / f"{question_id}_consensus.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(consensus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Consensus saved to {out_path}")

    return consensus


def load_consensus(question_id):
    """Load saved consensus from disk."""
    path = OUTPUT_DIR / "evidence" / f"{question_id}_consensus.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
