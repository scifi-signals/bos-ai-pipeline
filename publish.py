"""Publish pipeline output to the GitHub Pages site.

Copies rendered HTML from pipeline/output/html/ to articles/,
fixes internal links for the deployed directory structure,
copies social post JSON to social/,
and updates article_manifest.json (merge-based to preserve manual fields).
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
PIPELINE_DIR = ROOT / "pipeline"
HTML_DIR = PIPELINE_DIR / "output" / "html"
EVIDENCE_DIR = PIPELINE_DIR / "output" / "evidence"
SOCIAL_DIR = PIPELINE_DIR / "output" / "social"
QUESTIONS_DIR = PIPELINE_DIR / "questions"
ARTICLES_DIR = ROOT / "articles"
PUBLISHED_SOCIAL_DIR = ROOT / "social"
MANIFEST_PATH = ROOT / "article_manifest.json"


def publish():
    """Copy HTML output to articles/ and update manifest."""
    ARTICLES_DIR.mkdir(exist_ok=True)
    PUBLISHED_SOCIAL_DIR.mkdir(exist_ok=True)

    # Load existing manifest to preserve manual fields (e.g. demo)
    existing_manifest = {}
    if MANIFEST_PATH.exists():
        try:
            data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            for article in data.get("articles", []):
                existing_manifest[article["id"]] = article
        except (json.JSONDecodeError, KeyError):
            pass

    # Find all article HTML files
    article_files = sorted(HTML_DIR.glob("*_article.html"))
    if not article_files:
        print("No article HTML files found in pipeline/output/html/")
        return

    new_entries = {}
    for article_path in article_files:
        question_id = article_path.stem.replace("_article", "")
        evidence_path = HTML_DIR / f"{question_id}_evidence.html"

        # Copy article HTML
        dest_article = ARTICLES_DIR / article_path.name
        html = article_path.read_text(encoding="utf-8")

        # Fix evidence link: same directory (both in articles/)
        html = html.replace(
            f'href="{question_id}_evidence.html"',
            f'href="{question_id}_evidence.html"'
        )
        # Add "Back to Home" link in header
        html = html.replace(
            '<div class="header-right">',
            '<div class="header-right"><a href="../index.html">Home</a> &nbsp;|&nbsp; '
        )
        dest_article.write_text(html, encoding="utf-8")
        print(f"  Published: articles/{article_path.name}")

        # Copy evidence HTML
        if evidence_path.exists():
            dest_evidence = ARTICLES_DIR / evidence_path.name
            ehtml = evidence_path.read_text(encoding="utf-8")
            # Fix article link
            ehtml = ehtml.replace(
                f'href="{question_id}_article.html"',
                f'href="{question_id}_article.html"'
            )
            # Add "Back to Home" link
            ehtml = ehtml.replace(
                '<div class="header-right">',
                '<div class="header-right"><a href="../index.html">Home</a> &nbsp;|&nbsp; '
            )
            dest_evidence.write_text(ehtml, encoding="utf-8")
            print(f"  Published: articles/{evidence_path.name}")

        # Copy social posts
        has_social = False
        social_src = SOCIAL_DIR / f"{question_id}.json"
        if social_src.exists():
            social_dest = PUBLISHED_SOCIAL_DIR / f"{question_id}.json"
            shutil.copy2(social_src, social_dest)
            has_social = True
            print(f"  Published: social/{question_id}.json")

        # Build manifest entry from pipeline output metadata
        entry = _build_manifest_entry(question_id, has_social)
        if entry:
            new_entries[question_id] = entry

    # Merge: preserve manual fields from existing manifest
    merged = []
    # New articles first (not in existing manifest)
    for qid, entry in new_entries.items():
        if qid in existing_manifest:
            # Preserve manual fields from existing entry
            for key, value in existing_manifest[qid].items():
                if key not in entry:
                    entry[key] = value
        merged.append(entry)

    # Keep existing entries that aren't in new_entries (shouldn't happen normally,
    # but handles edge cases where HTML was deleted but manifest entry should stay)

    # Sort: newest first (articles not previously in manifest go to top)
    existing_ids = set(existing_manifest.keys())
    merged.sort(key=lambda e: (
        0 if e["id"] not in existing_ids else 1,
        e["id"],
    ))

    # Update manifest
    manifest = {"articles": merged}
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nManifest updated: {len(merged)} articles in article_manifest.json")


def _build_manifest_entry(question_id, has_social=False):
    """Build a manifest entry from pipeline output metadata."""
    entry = {
        "id": question_id,
        "title": question_id.replace("_", " ").title(),
        "article_url": f"articles/{question_id}_article.html",
        "evidence_url": f"articles/{question_id}_evidence.html",
        "tags": [],
        "sources_count": 0,
        "findings_count": 0,
        "fact_check": None,
    }

    if has_social:
        entry["has_social"] = True

    # Read question config for title and tags
    question_path = QUESTIONS_DIR / f"{question_id}.json"
    if question_path.exists():
        q = json.loads(question_path.read_text(encoding="utf-8"))
        entry["title"] = q.get("question", entry["title"])
        entry["tags"] = q.get("tags", [])

    # Read evidence package for counts
    evidence_path = EVIDENCE_DIR / f"{question_id}.json"
    if evidence_path.exists():
        ev = json.loads(evidence_path.read_text(encoding="utf-8"))
        entry["sources_count"] = ev.get("sources_processed", 0)
        entry["findings_count"] = ev.get("total_findings", 0)

    # Read fact-check result
    fc_path = EVIDENCE_DIR / f"{question_id}_factcheck.json"
    if fc_path.exists():
        fc = json.loads(fc_path.read_text(encoding="utf-8"))
        entry["fact_check"] = fc.get("overall_assessment", None)

    return entry


if __name__ == "__main__":
    print("Publishing pipeline output to site...\n")
    publish()
    print("\nDone.")
