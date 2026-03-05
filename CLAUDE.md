# Based on Science (BoS) AI Pipeline

AI pipeline for NASEM's "Based on Science" series. Discovers science questions, assesses evidence from authoritative sources, generates accessible article drafts at 8th-grade reading level.

## How to Run

```bash
python main.py run <question_id>        # Full pipeline
python main.py extract <question_id>    # Evidence extraction only
python main.py generate <question_id>   # Article from existing evidence
python main.py check <question_id>      # Fact-check existing article
python main.py evaluate <question_id>   # Compare to reference article
python main.py serve                    # Browse output at localhost:8080
```

## Pipeline

1. `source_loader.py` — Fetch/parse web pages + PDFs, chunk, cache to `sources/`
2. `evidence_extractor.py` — Claude extracts structured evidence per source
3. `consensus_builder.py` — Claude synthesizes cross-source consensus
4. `article_generator.py` — Claude generates BoS-style article from evidence
5. `fact_checker.py` — GPT-4o independently verifies claims + textstat reading level
6. `html_renderer.py` — Renders styled HTML using STM design system
7. `evaluate.py` — Compares generated article to published reference

## API Keys

Loaded from env vars or local text files:
- `ANTHROPIC_API_KEY` / `anthropic_api_key.txt` — Claude (evidence, consensus, article)
- `OPENAI_API_KEY` / `openai_api_key.txt` — GPT-4o (fact-checking)

## Key Design Decisions

- Claude for extraction/generation (better at structured analysis), GPT-4o for fact-checking (independent model prevents self-confirmation)
- Source tiers: Tier 1 (NAS/IPCC) > Tier 2 (govt agencies) > Tier 3 (individual studies) > Tier 4 (advocacy/journalism)
- Chunking at ~8000 tokens with 500-token overlap for long documents
- All evidence traced back to specific sources with exact quotes
- HTML uses STM design system (DM Sans + DM Serif Display, card layout)
