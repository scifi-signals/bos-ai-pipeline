"""Configuration for the BoS AI Pipeline."""

import os
import pathlib

# ========================
# API KEYS — environment variables only
# ========================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ========================
# MODEL SETTINGS
# ========================
CLAUDE_MODEL = "claude-sonnet-4-20250514"
GPT4O_MODEL = "gpt-4o"
CLAUDE_MAX_TOKENS = 8192
GPT4O_MAX_TOKENS = 4096

# ========================
# SOURCE TIERS
# ========================
SOURCE_TIERS = {
    1: "NAS/NASEM reports, IPCC reports, peer-reviewed meta-analyses",
    2: "Government agencies (EPA, USGCRP, CDC), major health organizations (WHO, HEI)",
    3: "Peer-reviewed individual studies, university research",
    4: "Health advocacy organizations, science journalism, educational resources",
}

# ========================
# CHUNKING
# ========================
CHUNK_MAX_CHARS = 32000   # ~8000 tokens
CHUNK_OVERLAP_CHARS = 2000  # ~500 tokens

# ========================
# PATHS
# ========================
PROJECT_DIR = pathlib.Path(__file__).parent
SOURCES_DIR = PROJECT_DIR / "sources"
OUTPUT_DIR = PROJECT_DIR / "output"
QUESTIONS_DIR = PROJECT_DIR / "questions"
REFERENCE_DIR = PROJECT_DIR / "reference"
