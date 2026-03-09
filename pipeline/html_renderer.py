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

.consensus-detail { font-size:12px; color:var(--text-secondary); margin-top:10px; }
.consensus-detail summary { cursor:pointer; list-style:none; display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-tertiary); }
.consensus-detail summary::before { content:"\\25B6"; font-size:9px; transition:transform 0.15s; }
.consensus-detail[open] summary::before { transform:rotate(90deg); }
.consensus-detail summary::-webkit-details-marker { display:none; }
.consensus-detail-body { margin-top:8px; padding:12px 16px; background:var(--bg); border-radius:var(--radius-sm); font-size:13px; line-height:1.6; }
.consensus-detail-body a { color:var(--accent); text-decoration:none; }
.consensus-detail-body a:hover { text-decoration:underline; }

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

.breadcrumbs { max-width:900px; margin:0 auto; padding:12px 32px 0; font-size:13px; color:var(--text-tertiary); }
.breadcrumbs a { color:var(--accent); text-decoration:none; font-weight:500; }
.breadcrumbs a:hover { text-decoration:underline; }
.breadcrumbs .sep { margin:0 6px; }

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
function replaceArticleUrls() {
    var articleUrl = window.location.href;
    document.querySelectorAll('.social-card-text').forEach(function(el) {
        el.textContent = el.textContent.replace(/\\{\\{ARTICLE_URL\\}\\}/g, articleUrl);
    });
}
document.addEventListener('DOMContentLoaded', replaceArticleUrls);

function copyPost(elementId, btn) {
    var el = document.getElementById(elementId);
    if (!el) return;
    var text = el.textContent;
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


def render_article_html(article_markdown, question_id, tags=None,
                        evidence=None, fact_check_result=None):
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

    # Verification card — trust signal after the short answer
    body_html += _render_verification_card(question_id, evidence, fact_check_result)

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
        breadcrumbs=[("Home", "../index.html"), (title,)],
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

    # Build source name → URL lookup from evidence package
    source_urls = {}
    for src in evidence_package.get("evidence", []):
        name = src.get("source", "")
        url = src.get("url", "")
        if name and url:
            source_urls[name] = url

    def _lookup_source_url(name):
        """Fuzzy source URL lookup — handles consensus using shortened names."""
        if name in source_urls:
            return source_urls[name]
        # Check if name is a substring of any evidence source (or vice versa)
        name_lower = name.lower()
        for src_name, url in source_urls.items():
            if name_lower in src_name.lower() or src_name.lower() in name_lower:
                return url
        return ""

    body_html = ""

    # Consensus overview
    if consensus and "primary_claims" in consensus:
        body_html += '<div class="card"><h2>Consensus Analysis</h2>'
        if consensus.get("overall_answer"):
            body_html += f'<p>{html_lib.escape(consensus["overall_answer"])}</p>'

        tier_labels = {1: "Tier 1 — national/international body", 2: "Tier 2 — government agency", 3: "Tier 3 — individual study", 4: "Tier 4 — journalism/advocacy"}

        for claim in consensus["primary_claims"]:
            level = claim.get("consensus_level", "limited")
            css_class = f"consensus-{level}"
            data_points = claim.get("key_data_points", [])
            supporting = claim.get("supporting_sources", [])
            contradicting = claim.get("contradicting_sources", [])
            uncertainties = claim.get("uncertainties", [])
            confidence_note = claim.get("confidence_note", "")

            # Claim + data points first
            body_html += f"""
            <div style="margin:16px 0; padding:12px 0; border-top:1px solid var(--border-light);">
                <strong>{html_lib.escape(claim.get('claim', ''))}</strong>
            """
            if data_points:
                body_html += '<ul style="margin:8px 0 0 20px;">'
                for dp in data_points:
                    src_name = dp.get("source", "")
                    src_url = _lookup_source_url(src_name)
                    if src_url:
                        src_html = f'<a href="{html_lib.escape(src_url)}" target="_blank" rel="noopener">{html_lib.escape(src_name)}</a>'
                    else:
                        src_html = html_lib.escape(src_name)
                    body_html += f'<li style="font-size:13px;">{html_lib.escape(dp.get("point", ""))} <span style="color:var(--text-tertiary);">— {src_html}</span></li>'
                body_html += '</ul>'

            # Confidence assessment as collapsible footnote below the evidence
            detail_lines = []
            if confidence_note:
                detail_lines.append(f'<p style="margin:0 0 8px;"><strong>Assessment:</strong> {html_lib.escape(confidence_note)}</p>')
            if supporting:
                for s in supporting:
                    name = s.get("source", "")
                    tier = s.get("tier", 0)
                    tier_desc = tier_labels.get(tier, "")
                    finding = s.get("key_finding", "")
                    src_url = _lookup_source_url(name)
                    if src_url:
                        src_link = f'<a href="{html_lib.escape(src_url)}" target="_blank" rel="noopener">{html_lib.escape(name)}</a>'
                    else:
                        src_link = html_lib.escape(name)
                    line = f'<p style="margin:0 0 4px;"><strong>Source:</strong> {src_link}'
                    if tier_desc:
                        line += f' <span style="color:var(--text-tertiary);">({tier_desc})</span>'
                    line += '</p>'
                    if finding:
                        line += f'<p style="margin:0 0 8px; padding-left:12px; font-style:italic; color:var(--text-secondary);">{html_lib.escape(finding)}</p>'
                    detail_lines.append(line)
            if contradicting:
                for s in contradicting:
                    name = s.get("source", "")
                    finding = s.get("key_finding", "")
                    src_url = _lookup_source_url(name)
                    if src_url:
                        src_link = f'<a href="{html_lib.escape(src_url)}" target="_blank" rel="noopener">{html_lib.escape(name)}</a>'
                    else:
                        src_link = html_lib.escape(name)
                    detail_lines.append(f'<p style="margin:0 0 4px; color:var(--red);"><strong>Contradicting:</strong> {src_link}</p>')
                    if finding:
                        detail_lines.append(f'<p style="margin:0 0 8px; padding-left:12px; font-style:italic; color:var(--text-secondary);">{html_lib.escape(finding)}</p>')
            if uncertainties:
                unc_items = "".join(f'<li>{html_lib.escape(u)}</li>' for u in uncertainties)
                detail_lines.append(f'<p style="margin:8px 0 4px;"><strong>Caveats:</strong></p><ul style="margin:0 0 0 20px; color:var(--text-secondary);">{unc_items}</ul>')

            if detail_lines:
                body_html += f"""
                <details class="consensus-detail">
                    <summary><span class="consensus-level {css_class}">{level}</span> confidence — click for details</summary>
                    <div class="consensus-detail-body">
                        {''.join(detail_lines)}
                    </div>
                </details>
                """

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
        if n_findings == 0:
            continue
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
        breadcrumbs=[("Home", "../index.html"), ("Article", f"{question_id}_article.html"), ("Evidence",)],
    )

    out_path = OUTPUT_DIR / "html" / f"{question_id}_evidence.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(f"  Evidence HTML saved to {out_path}")
    return out_path


def _wrap_page(title, hero, body, nav_extra="", include_js=False, include_social_js=False, description="", breadcrumbs=None):
    """Wrap content in full HTML page with STM design system."""
    js_parts = []
    if include_js:
        js_parts.append(TOGGLE_JS)
    if include_social_js:
        js_parts.append(SOCIAL_JS)
    js_block = f"<script>{''.join(js_parts)}</script>" if js_parts else ""
    og_desc = html_lib.escape(description) if description else html_lib.escape(title)
    # Build breadcrumb trail
    if breadcrumbs:
        crumb_parts = []
        for label, href in breadcrumbs[:-1]:
            crumb_parts.append(f'<a href="{html_lib.escape(href)}">{html_lib.escape(label)}</a>')
        crumb_parts.append(html_lib.escape(breadcrumbs[-1][0]))  # last item is current page, no link
        breadcrumb_html = '<div class="breadcrumbs">' + '<span class="sep">›</span>'.join(crumb_parts) + '</div>'
    else:
        breadcrumb_html = ""
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
                <a href="../index.html" style="display:flex;align-items:center;gap:16px;text-decoration:none;color:inherit;">
                <div class="logo-mark">BoS</div>
                <span class="header-title">Based on Science</span>
                </a>
            </div>
            <div class="header-right">{nav_extra}</div>
        </div>
    </div>
    {breadcrumb_html}
    {hero}
    <div class="container">
        {body}
    </div>
    <div class="footer">
        Based on Science &mdash; National Academies of Sciences, Engineering, and Medicine<br>
        AI-generated from authoritative sources, independently fact-checked.
        <a href="../methodology.html" style="color:var(--accent);">How it works</a>
    </div>
    {js_block}
</body>
</html>"""


def _render_verification_card(question_id, evidence=None, fact_check_result=None):
    """Render a trust/verification summary card for the article."""
    parts = []

    if evidence:
        sources = evidence.get("sources_processed", 0)
        findings = evidence.get("total_findings", 0)
        parts.append(f'<span style="font-weight:600;">{findings}</span> findings extracted from '
                      f'<span style="font-weight:600;">{sources}</span> authoritative sources')

    if fact_check_result:
        summary = fact_check_result.get("summary", {})
        confirmed = summary.get("confirmed", 0)
        total = confirmed + summary.get("plausible", 0) + summary.get("unsupported", 0) + summary.get("contradicted", 0)
        if total > 0:
            rl = fact_check_result.get("reading_level", {})
            fk = rl.get("flesch_kincaid_grade", "?")
            parts.append(f'<span style="font-weight:600;">{confirmed}/{total}</span> claims independently verified')
            try:
                fk_num = float(fk)
                if fk_num <= 10:
                    parts.append(f'Reading level: grade <span style="font-weight:600;">{fk}</span>')
            except (ValueError, TypeError):
                pass

    if not parts:
        return ""

    evidence_link = f'{question_id}_evidence.html'
    bullets = "".join(f'<div style="padding:3px 0;">{p}</div>' for p in parts)

    return f"""
    <div style="background:var(--green-light); border:1px solid #BBF7D0; border-radius:var(--radius);
                padding:16px 20px; margin-bottom:16px; font-size:13px; line-height:1.6;">
        <div style="font-weight:600; margin-bottom:6px; color:var(--green);">How this article was verified</div>
        {bullets}
        <div style="margin-top:8px; font-size:12px; color:var(--text-secondary);">
            Every claim was checked by an independent AI model (GPT-4o) against the original source documents.
            <a href="{evidence_link}" style="color:var(--accent); font-weight:500;">View full evidence package</a>
            &nbsp;·&nbsp;
            <a href="../methodology.html" style="color:var(--accent); font-weight:500;">Methodology</a>
        </div>
    </div>
    """


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
    # Links — escape URL in href to prevent XSS
    def _link_replace(m):
        link_text = html_lib.escape(m.group(1))
        url = html_lib.escape(m.group(2))
        return f'<a href="{url}">{link_text}</a>'
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _link_replace, text)
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
