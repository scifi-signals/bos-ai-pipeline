"""CLI orchestrator for the BoS AI Pipeline."""

import argparse
import json
import sys
from pathlib import Path

from config import QUESTIONS_DIR, OUTPUT_DIR


def load_question(question_id):
    """Load a question config from the questions directory."""
    path = QUESTIONS_DIR / f"{question_id}.json"
    if not path.exists():
        print(f"Error: Question config not found at {path}")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_run(args):
    """Full pipeline: extract -> consensus -> generate -> fact-check -> render."""
    question_config = load_question(args.question_id)
    print(f"\n{'='*60}")
    print(f"BoS Pipeline: {question_config['question']}")
    print(f"{'='*60}")

    # Step 1: Evidence extraction
    print(f"\n[1/7] Extracting evidence from {len(question_config['sources'])} sources...")
    from evidence_extractor import extract_evidence
    evidence = extract_evidence(question_config)
    print(f"  Total: {evidence['total_findings']} findings from {evidence['sources_processed']} sources")

    # Step 2: Consensus building
    print(f"\n[2/7] Building consensus...")
    from consensus_builder import build_consensus
    consensus = build_consensus(evidence)
    n_claims = len(consensus.get("primary_claims", []))
    print(f"  Found {n_claims} primary claims")

    # Step 3: Article generation
    print(f"\n[3/7] Generating article...")
    from article_generator import generate_article
    article_result = generate_article(consensus, evidence)

    # Step 4: Fact-checking
    print(f"\n[4/7] Fact-checking...")
    from fact_checker import fact_check
    fc_result = fact_check(article_result["article_markdown"], evidence)

    # Step 5: Social post generation
    print(f"\n[5/7] Generating social posts...")
    from social_generator import generate_social_posts
    generate_social_posts(article_result["article_markdown"], evidence, args.question_id)

    # Step 6: HTML rendering
    print(f"\n[6/7] Rendering HTML...")
    from html_renderer import render_article_html, render_evidence_html
    render_article_html(article_result["article_markdown"], args.question_id,
                        tags=question_config.get("tags", []))
    render_evidence_html(evidence, consensus=consensus, fact_check_result=fc_result)

    # Step 7: Evaluation (if reference exists)
    print(f"\n[7/7] Evaluation...")
    from evaluate import evaluate
    eval_result = evaluate(args.question_id)

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"  Article: output/articles/{args.question_id}.md")
    print(f"  HTML:    output/html/{args.question_id}_article.html")
    print(f"  Evidence: output/html/{args.question_id}_evidence.html")
    print(f"{'='*60}")


def cmd_extract(args):
    """Evidence extraction only."""
    question_config = load_question(args.question_id)
    print(f"\nExtracting evidence for: {question_config['question']}")

    from evidence_extractor import extract_evidence
    evidence = extract_evidence(question_config)
    print(f"\nDone. {evidence['total_findings']} findings from {evidence['sources_processed']} sources")


def cmd_generate(args):
    """Generate article from existing evidence."""
    question_config = load_question(args.question_id)
    print(f"\nGenerating article for: {question_config['question']}")

    from evidence_extractor import load_evidence
    evidence = load_evidence(args.question_id)
    if not evidence:
        print("Error: No evidence package found. Run 'extract' first.")
        sys.exit(1)

    from consensus_builder import build_consensus, load_consensus
    consensus = load_consensus(args.question_id)
    if not consensus:
        print("Building consensus first...")
        consensus = build_consensus(evidence)

    from article_generator import generate_article
    article_result = generate_article(consensus, evidence)

    from html_renderer import render_article_html
    render_article_html(article_result["article_markdown"], args.question_id,
                        tags=question_config.get("tags", []))
    print("\nDone.")


def cmd_check(args):
    """Fact-check existing article."""
    from article_generator import load_article
    article = load_article(args.question_id)
    if not article:
        print("Error: No article found. Run 'generate' first.")
        sys.exit(1)

    from evidence_extractor import load_evidence
    evidence = load_evidence(args.question_id)
    if not evidence:
        print("Error: No evidence package found. Run 'extract' first.")
        sys.exit(1)

    print(f"\nFact-checking article for: {evidence['question']}")
    from fact_checker import fact_check
    fact_check(article, evidence)
    print("\nDone.")


def cmd_evaluate(args):
    """Compare generated article to reference."""
    print(f"\nEvaluating: {args.question_id}")
    from evaluate import evaluate
    result = evaluate(args.question_id, reference_path=args.reference)
    if not result:
        print("Evaluation failed — missing generated or reference article.")


def cmd_serve(args):
    """Serve output directory for browsing."""
    import http.server
    import functools

    port = args.port or 8080
    html_dir = OUTPUT_DIR / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    # Generate index page
    _generate_index(html_dir)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(html_dir))
    with http.server.HTTPServer(("", port), handler) as httpd:
        print(f"Serving output at http://localhost:{port}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def _generate_index(html_dir):
    """Generate a simple index.html listing all articles."""
    articles = sorted(html_dir.glob("*_article.html"))
    links = []
    for a in articles:
        qid = a.stem.replace("_article", "")
        links.append(f'<li style="margin:8px 0;"><a href="{a.name}">{qid}</a> '
                     f'(<a href="{qid}_evidence.html">evidence</a>)</li>')

    if not links:
        links = ["<li>No articles generated yet. Run: python main.py run &lt;question_id&gt;</li>"]

    index = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>BoS Pipeline Output</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>body{{font-family:'DM Sans',sans-serif;max-width:600px;margin:60px auto;padding:0 20px;color:#1A1A18;}}
h1{{font-family:'DM Serif Display',serif;font-weight:400;}}
a{{color:#2563EB;text-decoration:none;font-weight:500;}}a:hover{{text-decoration:underline;}}
</style></head><body>
<h1>Based on Science</h1>
<p style="color:#6B6960;">AI Pipeline Output</p>
<ul style="list-style:none;padding:0;">{''.join(links)}</ul>
</body></html>"""

    (html_dir / "index.html").write_text(index, encoding="utf-8")


def cmd_discover(args):
    """Discover potential BoS questions from STM and podcast data."""
    from question_discoverer import discover_questions, print_discoveries
    questions = discover_questions(max_questions=args.count)
    print_discoveries(questions)


def cmd_sources(args):
    """Find NASEM publications relevant to a question."""
    from nasem_sourcer import find_nasem_sources

    if args.question_id:
        question_config = load_question(args.question_id)
        question = question_config["question"]
    else:
        question = args.query

    if not question:
        print("Error: provide a question_id or --query")
        sys.exit(1)

    print(f"\nFinding NASEM sources for: {question}\n")
    results = find_nasem_sources(question, max_results=args.count)

    print(f"\nTop {len(results)} NASEM publications:")
    for i, r in enumerate(results, 1):
        print(f"\n  {i}. [{r['score']}] {r['name']}")
        print(f"     {r['url']}")
        print(f"     Year: {r.get('year', '?')} | {r.get('description', '')[:100]}")


def main():
    parser = argparse.ArgumentParser(description="BoS AI Pipeline — Based on Science article generator")
    sub = parser.add_subparsers(dest="command", help="Pipeline commands")

    # run
    p = sub.add_parser("run", help="Full pipeline: extract -> consensus -> generate -> check -> render")
    p.add_argument("question_id", help="Question ID (matches JSON filename in questions/)")

    # extract
    p = sub.add_parser("extract", help="Extract evidence from sources")
    p.add_argument("question_id")

    # generate
    p = sub.add_parser("generate", help="Generate article from existing evidence")
    p.add_argument("question_id")

    # check
    p = sub.add_parser("check", help="Fact-check existing article")
    p.add_argument("question_id")

    # evaluate
    p = sub.add_parser("evaluate", help="Compare generated article to reference")
    p.add_argument("question_id")
    p.add_argument("--reference", help="Path to reference article (default: reference/<id>.md)")

    # discover
    p = sub.add_parser("discover", help="Discover potential BoS questions from STM + podcasts")
    p.add_argument("--count", type=int, default=10, help="Number of questions to return")

    # sources
    p = sub.add_parser("sources", help="Find NASEM publications for a question")
    p.add_argument("question_id", nargs="?", help="Question ID (optional)")
    p.add_argument("--query", help="Free-text question (alternative to question_id)")
    p.add_argument("--count", type=int, default=10, help="Number of results")

    # serve
    p = sub.add_parser("serve", help="Browse output at localhost")
    p.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "run": cmd_run,
        "extract": cmd_extract,
        "generate": cmd_generate,
        "check": cmd_check,
        "evaluate": cmd_evaluate,
        "discover": cmd_discover,
        "sources": cmd_sources,
        "serve": cmd_serve,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
