"""Extract structured evidence from sources via Claude."""

import json

from llm import ask_claude
from source_loader import fetch_source, chunk_text
from prompts.evidence_extraction import EVIDENCE_EXTRACTION_PROMPT
from config import SOURCE_TIERS, OUTPUT_DIR


def extract_evidence(question_config, force_fetch=False):
    """Extract evidence from all sources for a question. Returns evidence package."""
    question = question_config["question"]
    question_id = question_config["id"]
    all_evidence = []

    for source in question_config["sources"]:
        print(f"  Extracting from: {source['name']}...")
        try:
            source_data = fetch_source(source["url"], source.get("type", "web"), force=force_fetch)
            source_text = source_data.get("text", "")

            if not source_text.strip():
                print(f"    SKIP: No text content")
                all_evidence.append({
                    "source": source["name"],
                    "url": source["url"],
                    "tier": source.get("tier", 3),
                    "findings": [],
                    "note": "No text content extracted",
                })
                continue

            source_evidence = extract_from_source(
                source_text,
                question,
                source_meta={
                    "name": source["name"],
                    "url": source["url"],
                    "tier": source.get("tier", 3),
                    "type": source.get("type", "web"),
                },
            )
            n = len(source_evidence.get("findings", []))
            print(f"    Found {n} findings")
            all_evidence.append(source_evidence)

        except Exception as e:
            print(f"    ERROR: {e}")
            all_evidence.append({
                "source": source["name"],
                "url": source["url"],
                "tier": source.get("tier", 3),
                "error": str(e),
                "findings": [],
            })

    package = {
        "question": question,
        "question_id": question_id,
        "sources_processed": len(all_evidence),
        "total_findings": sum(len(e.get("findings", [])) for e in all_evidence),
        "evidence": all_evidence,
    }

    # Save evidence package
    out_path = OUTPUT_DIR / "evidence" / f"{question_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Evidence saved to {out_path}")

    return package


def extract_from_source(text, question, source_meta):
    """Extract evidence from a single source, handling chunking for long docs."""
    chunks = chunk_text(text, source_meta=source_meta)

    if len(chunks) == 1:
        return _extract_from_chunk(chunks[0]["text"], question, source_meta, 0, 1)

    print(f"    Processing {len(chunks)} chunks...")
    chunk_findings = []
    for chunk in chunks:
        result = _extract_from_chunk(
            chunk["text"], question, source_meta,
            chunk["chunk_index"], chunk["total_chunks"],
        )
        chunk_findings.append(result)

    return _merge_chunk_evidence(chunk_findings, source_meta)


def _extract_from_chunk(text, question, source_meta, chunk_index, total_chunks):
    """Extract evidence from a single text chunk via Claude."""
    tier_desc = SOURCE_TIERS.get(source_meta["tier"], "Unknown")
    context = f"Source: {source_meta['name']} (Tier {source_meta['tier']}: {tier_desc})"
    if total_chunks > 1:
        context += f"\nChunk {chunk_index + 1} of {total_chunks}"

    prompt = f"""{context}

Question: {question}

Source text:
---
{text[:30000]}
---

Extract all evidence relevant to the question above. Return JSON."""

    response = ask_claude(prompt, system_prompt=EVIDENCE_EXTRACTION_PROMPT)
    return _parse_json_response(response, source_meta)


def _parse_json_response(response, source_meta):
    """Parse JSON from LLM response, handling markdown code blocks."""
    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        parsed = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        parsed = {"findings": [], "parse_error": True, "raw_response": response[:500]}

    parsed["source"] = source_meta["name"]
    parsed["url"] = source_meta["url"]
    parsed["tier"] = source_meta["tier"]
    return parsed


def _merge_chunk_evidence(chunk_results, source_meta):
    """Merge evidence from multiple chunks, deduplicating by claim similarity."""
    all_findings = []
    seen_claims = set()

    for chunk_result in chunk_results:
        for finding in chunk_result.get("findings", []):
            # Simple dedup by normalized claim prefix
            claim_key = finding.get("claim", "").lower().strip()[:100]
            if claim_key and claim_key not in seen_claims:
                seen_claims.add(claim_key)
                all_findings.append(finding)

    return {
        "source": source_meta["name"],
        "url": source_meta["url"],
        "tier": source_meta["tier"],
        "findings": all_findings,
        "chunks_processed": len(chunk_results),
    }


def load_evidence(question_id):
    """Load saved evidence package from disk."""
    path = OUTPUT_DIR / "evidence" / f"{question_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
