# Based on Science (BoS) AI Pipeline

AI pipeline for NASEM's "Based on Science" series. Discovers science questions, assesses evidence from authoritative sources, generates accessible article drafts at 8th-grade reading level.

## How to Run

```bash
# Full pipeline (7 steps: extract → consensus → generate → fact-check → social → render → evaluate)
python main.py run <question_id>

# Individual steps
python main.py extract <question_id>    # Evidence extraction only
python main.py generate <question_id>   # Article from existing evidence
python main.py check <question_id>      # Fact-check existing article
python main.py evaluate <question_id>   # Compare to reference article

# Discovery + sources
python main.py discover --count 15      # Find BoS questions from STM/podcasts
python main.py sources <question_id>    # Find NASEM publications for a question

# Discovery orchestrator (writes discovered_questions.json + question configs)
python run_discovery.py

# Dev server
python main.py serve                    # Browse output at localhost:8080
```

## Pipeline (7 Steps)

1. `source_loader.py` — Fetch/parse web pages + PDFs, chunk, cache to `sources/`
2. `evidence_extractor.py` — Claude extracts structured evidence per source
3. `consensus_builder.py` — Claude synthesizes cross-source consensus
4. `article_generator.py` — Claude generates BoS-style article from evidence
5. `fact_checker.py` — GPT-4o independently verifies claims + textstat reading level
6. `social_generator.py` — Claude generates short + long social media posts
7. `html_renderer.py` — Renders styled HTML using STM design system

## Discovery Pipeline

- `question_discoverer.py` — Mines questions from STM trending topics, podcast claims, Reddit, and Google Trends
- `nasem_sourcer.py` — Finds relevant NASEM publications via keyword scoring + optional LLM rerank
- `reddit_sourcer.py` — Mines Reddit science/health subreddits for public questions and misconceptions (public JSON API, no auth needed)
- `trends_sourcer.py` — Mines Google Trends for rising science/health searches (pytrends, no API key)
- `alternative_sourcer.py` — Finds CDC/WHO/IPCC/Cochrane sources when NASEM has no coverage (gap analysis)
- `run_discovery.py` — Orchestrates discovery: find questions → NASEM sources → alternative sources for gaps → write configs + queue
- Data paths (`STM_DIR`, `PODCAST_DIR`) configurable via env vars for CI

## Workflows

- `generate-article.yml` — Manual dispatch: runs full pipeline, publishes article + social posts
- `discover-questions.yml` — Daily cron (8am ET) + manual: discovers questions, writes queue

## Landing Page Features

- Discovery Queue: shows pending questions (ready to generate), NASEM gaps (with alternative sources), and published articles
- One-Click Generation: "Generate Article" button triggers workflow via GitHub API dispatch
- Social Posts: short-form (X/Bluesky) + long-form (LinkedIn/Facebook) copy-paste cards

## API Keys

Loaded from env vars or local text files:
- `ANTHROPIC_API_KEY` — env var only, Claude (evidence, consensus, article, social, discovery)
- `OPENAI_API_KEY` — env var only, GPT-4o (fact-checking)

## Key Design Decisions

- Claude for extraction/generation (better at structured analysis), GPT-4o for fact-checking (independent model prevents self-confirmation)
- Source tiers: Tier 1 (NAS/IPCC) > Tier 2 (govt agencies) > Tier 3 (individual studies) > Tier 4 (advocacy/journalism)
- Chunking at ~8000 tokens with 500-token overlap for long documents
- All evidence traced back to specific sources with exact quotes
- HTML uses STM design system (DM Sans + DM Serif Display, card layout)
- `publish.py` uses merge-based manifest to preserve manual fields (e.g. `demo`)
- Discovery queue status determined client-side (cross-references manifest)
