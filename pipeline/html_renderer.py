"""Render articles and evidence as styled HTML using STM design system."""

import json
import re
import html as html_lib
from pathlib import Path
from config import OUTPUT_DIR

# STM Design System CSS — DM Sans + DM Serif Display, card-based layout
STM_CSS = """
:root {
    --bg: #FAFAF8; --surface: #FFFFFF; --surface-hover: #F5F5F0;
    --border: #E8E6E1; --border-light: #F0EEE9;
    --text-primary: #1A1A18; --text-secondary: #6B6960; --text-tertiary: #9B9890;
    --accent: #2563EB; --accent-light: #EFF6FF; --accent-hover: #1D4ED8;
    --green: #16A34A; --green-light: #F0FDF4;
    --amber: #D97706; --amber-light: #FFFBEB;
    --red: #DC2626; --red-light: #FEF2F2;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04); --shadow-md: 0 4px 12px rgba(0,0,0,0.06);
    --radius: 10px; --radius-sm: 6px;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'DM Sans',sans-serif; background:var(--bg); color:var(--text-primary); line-height:1.7; -webkit-font-smoothing:antialiased; }

.header { background:var(--surface); border-bottom:1px solid var(--border); padding:0 32px; }
.header-inner { max-width:900px; margin:0 auto; display:flex; align-items:center; justify-content:space-between; height:64px; }
.header-left { display:flex; align-items:center; gap:16px; }
.logo-mark { width:32px; height:32px; background:var(--accent); border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-weight:700; font-size:14px; }
.header-title { font-family:'DM Serif Display',serif; font-size:18px; }
.header-right { font-size:13px; color:var(--text-tertiary); }
.header-right a { color:var(--accent); text-decoration:none; font-weight:500; }

.hero { max-width:900px; margin:0 auto; padding:48px 32px 32px; }
.hero-org { font-size:12px; text-transform:uppercase; letter-spacing:1.5px; color:var(--text-tertiary); font-weight:600; margin-bottom:8px; }
.hero h1 { font-family:'DM Serif Display',serif; font-size:36px; font-weight:400; margin-bottom:12px; line-height:1.2; }
.hero .lede { font-size:17px; color:var(--text-secondary); font-style:italic; max-width:680px; line-height:1.6; }

.container { max-width:900px; margin:0 auto; padding:0 32px 60px; }

.card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:32px; margin-bottom:16px; box-shadow:var(--shadow-sm); }
.card:hover { box-shadow:var(--shadow-md); }
.card h2 { font-family:'DM Serif Display',serif; font-size:22px; font-weight:400; margin-bottom:16px; }
.card h3 { font-family:'DM Serif Display',serif; font-size:18px; font-weight:400; margin-top:20px; margin-bottom:8px; }
.card p { margin-bottom:14px; font-size:15px; }
.card strong { font-weight:600; }
.card em { font-style:italic; }
.card ul, .card ol { margin:12px 0; padding-left:24px; }
.card li { margin-bottom:6px; font-size:15px; }
.card a { color:var(--accent); text-decoration:none; font-weight:500; }
.card a:hover { text-decoration:underline; }

.short-answer { background:var(--accent-light); border:1px solid #BFDBFE; border-radius:var(--radius); padding:28px 32px; margin-bottom:16px; }
.short-answer h2 { font-family:'DM Serif Display',serif; font-size:22px; font-weight:400; margin-bottom:12px; color:var(--accent-hover); }
.short-answer p { font-size:16px; line-height:1.7; }

.note-box { background:var(--amber-light); border:1px solid #FDE68A; border-radius:var(--radius-sm); padding:16px 20px; margin:16px 0; font-size:14px; }

.resources-list { list-style:none; padding:0; }
.resources-list li { padding:10px 0; border-bottom:1px solid var(--border-light); }
.resources-list li:last-child { border-bottom:none; }
.resources-list a { color:var(--accent); text-decoration:none; font-weight:500; font-size:14px; }
.resources-list a:hover { text-decoration:underline; }

.tag-pills { display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }
.tag-pill { display:inline-block; padding:4px 12px; background:var(--bg); border:1px solid var(--border); border-radius:20px; font-size:12px; color:var(--text-secondary); font-weight:500; }

.evidence-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); margin-bottom:12px; overflow:hidden; }
.evidence-header { padding:16px 20px; cursor:pointer; display:flex; justify-content:space-between; align-items:center; }
.evidence-header:hover { background:var(--surface-hover); }
.evidence-header h3 { font-family:'DM Serif Display',serif; font-size:16px; font-weight:400; }
.tier-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; }
.tier-1 { background:var(--green-light); color:var(--green); }
.tier-2 { background:var(--accent-light); color:var(--accent); }
.tier-3 { background:var(--amber-light); color:var(--amber); }
.tier-4 { background:var(--bg); color:var(--text-tertiary); }
.evidence-body { padding:0 20px 16px; display:none; }
.evidence-body.open { display:block; }
.finding { padding:12px 0; border-top:1px solid var(--border-light); }
.finding:first-child { border-top:none; }
.finding-claim { font-weight:600; font-size:14px; margin-bottom:4px; }
.finding-quote { font-style:italic; font-size:13px; color:var(--text-secondary); padding:8px 12px; border-left:3px solid var(--border); margin:8px 0; }
.finding-meta { font-size:12px; color:var(--text-tertiary); display:flex; gap:12px; }
.strength-strong { color:var(--green); font-weight:600; }
.strength-moderate { color:var(--amber); font-weight:600; }
.strength-limited { color:var(--text-tertiary); font-weight:600; }

.consensus-bar { display:flex; align-items:center; gap:8px; margin:8px 0; }
.consensus-level { padding:3px 10px; border-radius:4px; font-size:12px; font-weight:600; text-transform:uppercase; }
.consensus-strong { background:var(--green-light); color:var(--green); }
.consensus-moderate { background:var(--amber-light); color:var(--amber); }
.consensus-limited { background:var(--red-light); color:var(--red); }
.consensus-conflicting { background:var(--bg); color:var(--text-tertiary); }

.fact-check-row { display:flex; align-items:flex-start; gap:12px; padding:10px 0; border-bottom:1px solid var(--border-light); }
.fact-check-row:last-child { border-bottom:none; }
.verdict-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; text-transform:uppercase; white-space:nowrap; }
.verdict-CONFIRMED { background:var(--green-light); color:var(--green); }
.verdict-PLAUSIBLE { background:var(--accent-light); color:var(--accent); }
.verdict-UNSUPPORTED { background:var(--amber-light); color:var(--amber); }
.verdict-CONTRADICTED { background:var(--red-light); color:var(--red); }

.footer { max-width:900px; margin:0 auto; padding:20px 32px 40px; text-align:center; font-size:12px; color:var(--text-tertiary); border-top:1px solid var(--border-light); }

.social-share { margin-top:16px; }
.social-share h2 { font-family:'DM Serif Display',serif; font-size:22px; font-weight:400; margin-bottom:16px; }
.social-cards { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.social-card { background:var(--bg); border:1px solid var(--border-light); border-radius:var(--radius-sm); padding:16px; }
.social-card-label { font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-tertiary); font-weight:600; margin-bottom:8px; }
.social-card-text { font-size:13px; line-height:1.5; color:var(--text-primary); white-space:pre-wrap; margin-bottom:10px; }
.copy-btn { display:inline-block; padding:4px 12px; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-sm); font-size:12px; font-weight:500; cursor:pointer; color:var(--text-secondary); font-family:'DM Sans',sans-serif; }
.copy-btn:hover { background:var(--surface-hover); color:var(--text-primary); }
.copy-btn.copied { background:var(--green-light); color:var(--green); border-color:var(--green); }

@media (max-width:640px) {
    .header { padding:0 16px; }
    .hero, .container { padding-left:16px; padding-right:16px; }
    .hero h1 { font-size:28px; }
    .card, .short-answer { padding:20px; }
    .social-cards { grid-template-columns:1fr; }
}
"""

TOGGLE_JS = """
function toggleEvidence(id) {
    var body = document.getElementById(id);
    body.classList.toggle('open');
    var arrow = body.previousElementSibling.querySelector('.arrow');
    arrow.textContent = body.classList.contains('open') ? '\\u25BC' : '\\u25B6';
}
"""

SOCIAL_JS = """
function copyPost(elementId, btn) {
    var el = document.getElementById(elementId);
    if (!el) return;
    var text = el.textContent.replace(/\\{\\{ARTICLE_URL\\}\\}/g, window.location.href);
    navigator.clipboard.writeText(text).then(function() {
        btn.textContent = 'Copied!';
        btn.className = 'copy-btn copied';
        setTimeout(function() {
            btn.textContent = 'Copy';
            btn.className = 'copy-btn';
        }, 2000);
    });
}
"""


def render_article_html(article_markdown, question_id, tags=None):
    """Render a BoS article as styled HTML."""
    sections = _parse_article_sections(article_markdown)
    tags = tags or []

    body_html = ""

    # Hero section — title and lede
    title = sections.get("title", "Based on Science")
    lede = sections.get("lede", "")
    hero_html = f"""
    <div class="hero">
        <div class="hero-org">National Academies of Sciences, Engineering, and Medicine</div>
        <h1>{html_lib.escape(title)}</h1>
        <p class="lede">{html_lib.escape(lede)}</p>
    </div>
    """

    # Short Answer — special styling
    if "The Short Answer" in sections:
        body_html += f"""
        <div class="short-answer">
            <h2>The Short Answer</h2>
            {_md_to_html(sections["The Short Answer"])}
        </div>
        """

    # Body sections
    for name, content in sections.items():
        if name in ("title", "lede", "subtitle", "The Short Answer", "Additional Resources", "tags_raw"):
            continue
        body_html += f"""
        <div class="card">
            <h2>{html_lib.escape(name)}</h2>
            {_md_to_html(content)}
        </div>
        """

    # Additional Resources
    if "Additional Resources" in sections:
        resources_html = _render_resources(sections["Additional Resources"])
        body_html += f"""
        <div class="card">
            <h2>Additional Resources</h2>
            <ul class="resources-list">{resources_html}</ul>
        </div>
        """

    # Tags
    if tags:
        pills = "".join(f'<span class="tag-pill">{html_lib.escape(t)}</span>' for t in tags)
        body_html += f'<div style="margin-top:16px;"><div class="tag-pills">{pills}</div></div>'

    # Social posts (if available)
    social_html, include_social_js = _render_social_section(question_id)
    body_html += social_html

    page = _wrap_page(
        title=title,
        hero=hero_html,
        body=body_html,
        nav_extra=f'<a href="{question_id}_evidence.html">View Evidence</a>',
        description=lede,
        include_social_js=include_social_js,
    )

    out_path = OUTPUT_DIR / "html" / f"{question_id}_article.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"  Article HTML saved to {out_path}")
    return out_path


def render_evidence_html(evidence_package, consensus=None, fact_check_result=None):
    """Render the evidence page with collapsible source cards."""
    question = evidence_package["question"]
    question_id = evidence_package["question_id"]

    body_html = ""

    # Consensus overview
    if consensus and "primary_claims" in consensus:
        body_html += '<div class="card"><h2>Consensus Analysis</h2>'
        if consensus.get("overall_answer"):
            body_html += f'<p>{html_lib.escape(consensus["overall_answer"])}</p>'

        for claim in consensus["primary_claims"]:
            level = claim.get("consensus_level", "limited")
            css_class = f"consensus-{level}"
            body_html += f"""
            <div style="margin:16px 0; padding:12px 0; border-top:1px solid var(--border-light);">
                <div class="consensus-bar">
                    <span class="consensus-level {css_class}">{level}</span>
                    <strong>{html_lib.escape(claim.get('claim', ''))}</strong>
                </div>
            """
            if claim.get("key_data_points"):
                body_html += '<ul style="margin:8px 0 0 20px;">'
                for dp in claim["key_data_points"]:
                    body_html += f'<li style="font-size:13px;">{html_lib.escape(dp.get("point", ""))} <span style="color:var(--text-tertiary);">— {html_lib.escape(dp.get("source", ""))}</span></li>'
                body_html += '</ul>'
            body_html += '</div>'
        body_html += '</div>'

    # Fact-check results
    if fact_check_result and "claims" in fact_check_result:
        summary = fact_check_result.get("summary", {})
        rl = fact_check_result.get("reading_level", {})
        assessment = fact_check_result.get("overall_assessment", "?")
        assessment_color = {"PASS": "var(--green)", "NEEDS_REVISION": "var(--amber)", "FAIL": "var(--red)"}.get(assessment, "var(--text-secondary)")

        body_html += f"""
        <div class="card">
            <h2>Fact-Check Report</h2>
            <div style="display:flex; gap:24px; flex-wrap:wrap; margin-bottom:16px;">
                <div><strong>Overall:</strong> <span style="color:{assessment_color}; font-weight:700;">{assessment}</span></div>
                <div><strong>Confirmed:</strong> {summary.get('confirmed', 0)}</div>
                <div><strong>Plausible:</strong> {summary.get('plausible', 0)}</div>
                <div><strong>Unsupported:</strong> {summary.get('unsupported', 0)}</div>
                <div><strong>Contradicted:</strong> {summary.get('contradicted', 0)}</div>
            </div>
            <div style="margin-bottom:16px;">
                <strong>Reading Level:</strong> FK Grade {rl.get('flesch_kincaid_grade', '?')}
                {'<span style="color:var(--green);"> (target met)</span>' if rl.get('target_met') else '<span style="color:var(--red);"> (above target)</span>'}
                &nbsp;|&nbsp; Flesch Ease: {rl.get('flesch_reading_ease', '?')}
                &nbsp;|&nbsp; Gunning Fog: {rl.get('gunning_fog', '?')}
            </div>
        """
        for c in fact_check_result["claims"]:
            verdict = c.get("verdict", "?")
            body_html += f"""
            <div class="fact-check-row">
                <span class="verdict-badge verdict-{verdict}">{verdict}</span>
                <div>
                    <div style="font-size:14px; font-weight:500;">{html_lib.escape(c.get('claim', ''))}</div>
                    <div style="font-size:12px; color:var(--text-tertiary); margin-top:2px;">{html_lib.escape(c.get('explanation', ''))}</div>
                </div>
            </div>
            """
        body_html += '</div>'

    # Source evidence cards (collapsible)
    body_html += '<div class="card"><h2>Source Evidence</h2></div>'
    for i, src in enumerate(evidence_package.get("evidence", [])):
        if src.get("error"):
            continue
        tier = src.get("tier", 3)
        n_findings = len(src.get("findings", []))
        card_id = f"evidence-{i}"

        source_name = html_lib.escape(src.get('source', 'Unknown'))
        source_url = src.get('url', '')
        source_link = f'<a href="{html_lib.escape(source_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">{source_name}</a>' if source_url else source_name

        body_html += f"""
        <div class="evidence-card">
            <div class="evidence-header" onclick="toggleEvidence('{card_id}')">
                <div>
                    <span class="tier-badge tier-{tier}">Tier {tier}</span>
                    &nbsp;
                    <h3 style="display:inline;">{source_link}</h3>
                    <span style="color:var(--text-tertiary); font-size:13px;"> — {n_findings} findings</span>
                </div>
                <span class="arrow" style="font-size:12px;">&#9654;</span>
            </div>
            <div class="evidence-body" id="{card_id}">
        """
        for finding in src.get("findings", []):
            strength = finding.get("strength", "limited")
            strength_class = f"strength-{strength}"
            body_html += f"""
                <div class="finding">
                    <div class="finding-claim">{html_lib.escape(finding.get('claim', ''))}</div>
            """
            if finding.get("evidence_quote"):
                body_html += f'<div class="finding-quote">{html_lib.escape(finding["evidence_quote"])}</div>'
            body_html += f"""
                    <div class="finding-meta">
                        <span class="{strength_class}">{strength}</span>
            """
            if finding.get("limitations"):
                body_html += f'<span>Limitations: {html_lib.escape(finding["limitations"])}</span>'
            body_html += '</div></div>'

        body_html += '</div></div>'

    hero_html = f"""
    <div class="hero">
        <div class="hero-org">Evidence Package</div>
        <h1>{html_lib.escape(question)}</h1>
        <p class="lede">{evidence_package.get('total_findings', 0)} findings from {evidence_package.get('sources_processed', 0)} sources</p>
    </div>
    """

    evidence_desc = f"{evidence_package.get('total_findings', 0)} findings from {evidence_package.get('sources_processed', 0)} sources"
    page = _wrap_page(
        title=f"Evidence: {question}",
        hero=hero_html,
        body=body_html,
        nav_extra=f'<a href="{question_id}_article.html">View Article</a>',
        include_js=True,
        description=evidence_desc,
    )

    out_path = OUTPUT_DIR / "html" / f"{question_id}_evidence.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"  Evidence HTML saved to {out_path}")
    return out_path


def _wrap_page(title, hero, body, nav_extra="", include_js=False, include_social_js=False, description=""):
    """Wrap content in full HTML page with STM design system."""
    js_parts = []
    if include_js:
        js_parts.append(TOGGLE_JS)
    if include_social_js:
        js_parts.append(SOCIAL_JS)
    js_block = f"<script>{''.join(js_parts)}</script>" if js_parts else ""
    og_desc = html_lib.escape(description) if description else html_lib.escape(title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_lib.escape(title)} | Based on Science</title>
    <meta property="og:title" content="{html_lib.escape(title)} | Based on Science">
    <meta property="og:description" content="{og_desc}">
    <meta property="og:type" content="article">
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Serif+Display&display=swap" rel="stylesheet">
    <style>{STM_CSS}</style>
</head>
<body>
    <div class="header">
        <div class="header-inner">
            <div class="header-left">
                <div class="logo-mark">BoS</div>
                <span class="header-title">Based on Science</span>
            </div>
            <div class="header-right">{nav_extra}</div>
        </div>
    </div>
    {hero}
    <div class="container">
        {body}
    </div>
    <div class="footer">
        Based on Science &mdash; National Academies of Sciences, Engineering, and Medicine<br>
        Generated by BoS AI Pipeline
    </div>
    {js_block}
</body>
</html>"""


def _render_social_section(question_id):
    """Render social post cards if social JSON exists. Returns (html, needs_js)."""
    social_path = OUTPUT_DIR / "social" / f"{question_id}.json"
    if not social_path.exists():
        return "", False

    try:
        data = json.loads(social_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "", False

    short_post = html_lib.escape(data.get("short_post", ""))
    long_post = html_lib.escape(data.get("long_post", ""))

    html = f"""
    <div class="card social-share">
        <h2>Share This Article</h2>
        <div class="social-cards">
            <div class="social-card">
                <div class="social-card-label">Short Post (X / Bluesky / Threads)</div>
                <div class="social-card-text" id="social-short">{short_post}</div>
                <button class="copy-btn" onclick="copyPost('social-short', this)">Copy</button>
            </div>
            <div class="social-card">
                <div class="social-card-label">Long Post (LinkedIn / Facebook)</div>
                <div class="social-card-text" id="social-long">{long_post}</div>
                <button class="copy-btn" onclick="copyPost('social-long', this)">Copy</button>
            </div>
        </div>
    </div>
    """
    return html, True


def _parse_article_sections(markdown):
    """Parse a BoS markdown article into named sections."""
    sections = {}
    lines = markdown.split("\n")
    current_section = None
    current_lines = []

    for line in lines:
        # H1 = title
        if line.startswith("# ") and "title" not in sections:
            sections["title"] = line[2:].strip()
            continue

        # **Based on Science** subtitle
        if line.strip() == "**Based on Science**":
            sections["subtitle"] = "Based on Science"
            continue

        # Italicized lede
        if line.strip().startswith("*") and line.strip().endswith("*") and "lede" not in sections and "title" in sections:
            sections["lede"] = line.strip().strip("*").strip()
            continue

        # H2 = section header
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[3:].strip()
            current_lines = []
            continue

        # Horizontal rules
        if line.strip() == "---":
            continue

        # Tags line
        if line.strip().startswith("*Tags:"):
            sections["tags_raw"] = line.strip().strip("*").replace("Tags:", "").strip()
            continue

        if current_section:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def _md_to_html(text):
    """Convert simple markdown to HTML (paragraphs, bold, italic, links, lists)."""
    paragraphs = re.split(r'\n\n+', text.strip())
    result = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Check for list
        lines = para.split("\n")
        if all(re.match(r'^\s*[-*]\s+', l) for l in lines if l.strip()):
            items = []
            for l in lines:
                l = re.sub(r'^\s*[-*]\s+', '', l)
                items.append(f"<li>{_inline_md(l)}</li>")
            result.append(f"<ul>{''.join(items)}</ul>")
            continue

        # Check for note box
        if para.startswith("**Important note:**") or para.startswith("**Important:**"):
            result.append(f'<div class="note-box">{_inline_md(para)}</div>')
            continue

        result.append(f"<p>{_inline_md(para)}</p>")

    return "\n".join(result)


def _inline_md(text):
    """Convert inline markdown: bold, italic, links."""
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    # Italic
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    return text


def _render_resources(text):
    """Render Additional Resources section as list items."""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Parse markdown link
        match = re.match(r'[-*]\s*\[([^\]]+)\]\(([^)]+)\)', line)
        if match:
            name, url = match.group(1), match.group(2)
            items.append(f'<li><a href="{html_lib.escape(url)}" target="_blank">{html_lib.escape(name)}</a></li>')
        else:
            # Plain text item
            line = re.sub(r'^[-*]\s*', '', line)
            items.append(f'<li>{html_lib.escape(line)}</li>')
    return "\n".join(items)
