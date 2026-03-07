"""Fetch, parse, chunk, and cache source documents."""

import hashlib
import json
import re
from pathlib import Path

import httpx

from config import SOURCES_DIR, CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS

SOURCES_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "BoS-AI-Pipeline/1.0 (NASEM research tool)"}

# Chapters to fetch from NASEM online reader (Summary + key content chapters)
NASEM_CHAPTERS = [2, 3, 4, 5]  # Summary, Introduction, and first two content chapters

_NASEM_PUB_RE = re.compile(r"https?://www\.nationalacademies\.org/publications/(\d+)")


def _cache_path(url):
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return SOURCES_DIR / f"{url_hash}.json"


def fetch_source(url, source_type="web", force=False):
    """Fetch and cache a source document. Returns dict with title, text, metadata."""
    cached = _cache_path(url)
    if cached.exists() and not force:
        return json.loads(cached.read_text(encoding="utf-8"))

    print(f"    Fetching: {url}")

    # NASEM publication landing pages have almost no content.
    # Fetch the online reader chapters instead.
    nasem_match = _NASEM_PUB_RE.match(url)
    if nasem_match and source_type != "pdf":
        result = _fetch_nasem_reader(nasem_match.group(1))
    elif source_type == "pdf":
        result = _fetch_pdf(url)
    else:
        result = _fetch_web(url)

    result["url"] = url
    result["source_type"] = source_type
    cached.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _fetch_nasem_reader(pub_id):
    """Fetch key chapters from the NASEM online reader for a publication."""
    from readability import Document
    from bs4 import BeautifulSoup

    base_url = f"https://www.nationalacademies.org/read/{pub_id}"
    all_text = []
    title = ""

    for chapter_num in NASEM_CHAPTERS:
        chapter_url = f"{base_url}/chapter/{chapter_num}"
        try:
            resp = httpx.get(chapter_url, follow_redirects=True, timeout=30, headers=HEADERS)
            if resp.status_code == 404:
                break  # No more chapters
            resp.raise_for_status()
            doc = Document(resp.text)
            if not title:
                title = doc.title()
            soup = BeautifulSoup(doc.summary(), "html.parser")
            chapter_text = soup.get_text(separator="\n", strip=True)
            if chapter_text.strip():
                all_text.append(f"[Chapter {chapter_num}]\n{chapter_text}")
        except Exception as e:
            print(f"    Warning: Could not fetch chapter {chapter_num}: {e}")
            continue

    full_text = "\n\n".join(all_text)

    if not full_text.strip():
        # Fall back to landing page if reader fails
        return _fetch_web(f"https://www.nationalacademies.org/publications/{pub_id}")

    print(f"    NASEM reader: {len(NASEM_CHAPTERS)} chapters, {len(full_text)} chars")
    return {"title": title, "text": full_text, "content_type": "nasem_reader", "char_count": len(full_text)}


def _fetch_web(url):
    """Fetch a web page and extract main content using readability."""
    resp = httpx.get(url, follow_redirects=True, timeout=30, headers=HEADERS)
    resp.raise_for_status()

    from readability import Document
    from bs4 import BeautifulSoup

    doc = Document(resp.text)
    title = doc.title()
    soup = BeautifulSoup(doc.summary(), "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    return {"title": title, "text": text, "content_type": "web", "char_count": len(text)}


def _fetch_pdf(url):
    """Fetch a PDF and extract text page-by-page."""
    resp = httpx.get(url, follow_redirects=True, timeout=60, headers=HEADERS)
    resp.raise_for_status()

    import io
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(resp.content))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page": i + 1, "text": text})

    full_text = "\n\n".join(f"[Page {p['page']}]\n{p['text']}" for p in pages)
    return {
        "title": f"PDF document ({len(pages)} pages)",
        "text": full_text,
        "content_type": "pdf",
        "page_count": len(pages),
        "char_count": len(full_text),
    }


def chunk_text(text, source_meta=None, max_chars=None, overlap=None):
    """Split text into overlapping chunks for processing long documents."""
    max_chars = max_chars or CHUNK_MAX_CHARS
    overlap = overlap or CHUNK_OVERLAP_CHARS

    if len(text) <= max_chars:
        return [{"text": text, "chunk_index": 0, "total_chunks": 1, "source_meta": source_meta}]

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = start + max_chars

        # Try to break at a paragraph boundary
        if end < len(text):
            para_break = text.rfind("\n\n", start + max_chars // 2, end)
            if para_break > start:
                end = para_break

        chunk_str = text[start:end]
        chunks.append({
            "text": chunk_str,
            "chunk_index": chunk_index,
            "source_meta": source_meta,
        })

        # Advance with overlap
        start = end - overlap if end < len(text) else len(text)
        chunk_index += 1

    for c in chunks:
        c["total_chunks"] = len(chunks)

    return chunks


def load_question_sources(question_config, force=False):
    """Fetch all sources for a question config. Returns list of source dicts."""
    results = []
    for source in question_config["sources"]:
        try:
            data = fetch_source(source["url"], source.get("type", "web"), force=force)
            data["name"] = source["name"]
            data["tier"] = source.get("tier", 3)
            results.append(data)
            print(f"    OK: {source['name']} ({data.get('char_count', '?')} chars)")
        except Exception as e:
            print(f"    FAILED: {source['name']} — {e}")
            results.append({
                "name": source["name"],
                "url": source["url"],
                "tier": source.get("tier", 3),
                "text": "",
                "error": str(e),
            })
    return results
