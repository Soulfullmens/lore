#!/usr/bin/env python3
"""Lore Static Site Generator — Agent-SEO & Human Web Presence.

Generates:
  - site/dist/index.html — Registry index page with search/filtering
  - site/dist/lessons/<slug>.html — High-contrast, symptom-indexed static page per lesson
  - site/dist/lessons/<slug>.md — Markdown mirror per lesson
  - site/dist/llms.txt — LLM index file for AI crawlers
  - site/dist/llms-full.txt — Full text concatenated corpus for context windows
  - site/dist/sitemap.xml — Sitemap for crawlers
  - site/dist/robots.txt — AI crawler permissions file
"""

from __future__ import annotations

import glob
import html
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SITE_DOMAIN = "https://lore-commons.dev"
REPO_URL = "https://github.com/Soulfullmens/lore"


def load_lessons(repo_root: Path) -> list[dict[str, Any]]:
    lessons = []
    for path in sorted(repo_root.glob("lessons/**/*.json")):
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
            content["_file_path"] = str(path.relative_to(repo_root))
            content["_slug"] = path.stem
            lessons.append(content)
        except Exception as e:
            print(f"Warning: failed to load {path}: {e}")
    return lessons


def render_html_header(title: str, description: str, json_ld: dict[str, Any] | None = None) -> str:
    escaped_title = html.escape(title)
    escaped_desc = html.escape(description)
    json_ld_script = ""
    if json_ld:
        json_ld_script = f'<script type="application/ld+json">\n{json.dumps(json_ld, indent=2)}\n</script>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_title}</title>
  <meta name="description" content="{escaped_desc}">
  <meta name="robots" content="index, follow">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  {json_ld_script}
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #3b82f6;
      --accent-glow: rgba(59, 130, 246, 0.15);
      --green: #10b981;
      --yellow: #f59e0b;
      --red: #ef4444;
      --code-bg: #030712;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 2.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
    }}
    header h1 {{
      font-size: 1.875rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }}
    header h1 a {{
      color: inherit;
      text-decoration: none;
    }}
    .tagline {{
      color: var(--text-muted);
      font-size: 1rem;
      margin-top: 0.5rem;
    }}
    .badge {{
      display: inline-block;
      padding: 0.25rem 0.625rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge-verified {{ background: rgba(16, 185, 129, 0.2); color: var(--green); border: 1px solid var(--green); }}
    .badge-draft {{ background: rgba(245, 158, 11, 0.2); color: var(--yellow); border: 1px solid var(--yellow); }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }}
    h2 {{
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 1rem;
      color: #fff;
    }}
    .symptoms-list {{
      list-style: none;
      margin-bottom: 1rem;
    }}
    .symptoms-list li {{
      font-family: 'JetBrains Mono', monospace;
      background: var(--code-bg);
      border: 1px solid var(--border);
      color: #f87171;
      padding: 0.5rem 0.75rem;
      border-radius: 0.375rem;
      margin-bottom: 0.5rem;
      font-size: 0.875rem;
      word-break: break-all;
    }}
    ol, ul {{
      padding-left: 1.25rem;
      margin-bottom: 1rem;
    }}
    li {{ margin-bottom: 0.5rem; }}
    code {{
      font-family: 'JetBrains Mono', monospace;
      background: var(--code-bg);
      padding: 0.2rem 0.4rem;
      border-radius: 0.25rem;
      font-size: 0.875rem;
    }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 1rem;
      border-radius: 0.5rem;
      overflow-x: auto;
      margin-bottom: 1rem;
    }}
    pre code {{
      padding: 0;
      background: none;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-top: 1rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    footer {{
      margin-top: 3rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      text-align: center;
      color: var(--text-muted);
      font-size: 0.875rem;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1><a href="/">📜 Lore Commons</a></h1>
      <p class="tagline">A verified experience commons for AI agents — machine-first, symptom-indexed, proven by execution.</p>
    </header>
"""


def render_html_footer() -> str:
    return f"""
    <footer>
      <p>Lore Registry v0.2.0 • Licensed CC-BY-4.0 (Lessons) & Apache-2.0 (Code) • <a href="{REPO_URL}">GitHub Repository</a></p>
    </footer>
  </div>
</body>
</html>
"""


def generate_lesson_markdown(lesson: dict[str, Any]) -> str:
    lines = [
        f"# {lesson['id']}",
        "",
        f"**Summary:** {lesson.get('summary', '')}",
        f"**Semver:** {lesson.get('semver', '')} | **Kind:** `{lesson.get('kind', '')}` | **Status:** `{lesson.get('lifecycle', {}).get('status', 'draft')}`",
        "",
        "## Verbatim Symptoms",
        "",
    ]
    for s in lesson.get("symptoms", []):
        lines.append(f"- `{s}`")
    lines.append("")

    lines.append("## Problem Statement")
    lines.append(lesson.get("problem", ""))
    lines.append("")

    lines.append("## Correct Procedure")
    for idx, step in enumerate(lesson.get("procedure", []), 1):
        lines.append(f"{idx}. {step}")
    lines.append("")

    lines.append("## Anti-Patterns")
    for ap in lesson.get("anti_patterns", []):
        lines.append(f"- {ap}")
    lines.append("")

    lines.append("## Documented Dead Ends")
    for fa in lesson.get("failed_attempts", []):
        lines.append(f"- **Approach:** {fa.get('approach', '')}")
        lines.append(f"  - *Why it fails:* {fa.get('why_it_fails', '')}")
        lines.append(f"  - *Time wasted:* ~{fa.get('time_wasted_estimate_min', 0)} mins")
    lines.append("")

    v = lesson.get("verification", {})
    lines.append("## Executable Verification Evals")
    lines.append(f"- **Docker Image:** `{v.get('image', '')}`")
    lines.append(f"- **Setup Network:** `{v.get('setup_network', 'packages')}` | **Eval Network:** `{v.get('network', 'none')}`")
    lines.append(f"- **Fix Command:** `{v.get('run', '')}`")
    if v.get("broken_run"):
        lines.append(f"- **Broken Command:** `{v.get('broken_run', '')}`")
    lines.append("")

    return "\n".join(lines)


def generate_lesson_html(lesson: dict[str, Any]) -> str:
    slug = lesson["_slug"]
    symptoms_str = " | ".join(lesson.get("symptoms", []))
    title = f"{symptoms_str} — Lore Lesson {slug}"
    desc = lesson.get("summary", "")

    status = lesson.get("lifecycle", {}).get("status", "draft")
    badge_class = "badge-verified" if status == "verified" else "badge-draft"

    # JSON-LD TechArticle
    json_ld = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": title,
        "description": desc,
        "articleBody": lesson.get("problem", ""),
        "dateModified": lesson.get("lifecycle", {}).get("last_verified", datetime.now(timezone.utc).isoformat()),
        "author": {
            "@type": "Person",
            "name": lesson.get("provenance", {}).get("author_human", "Soulfullmens")
        },
        "publisher": {
            "@type": "Organization",
            "name": "Lore Commons",
            "url": SITE_DOMAIN
        }
    }

    body = render_html_header(title, desc, json_ld)

    body += f"""
    <main>
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1rem;">
          <div>
            <span class="badge {badge_class}">{status}</span>
            <span style="color: var(--text-muted); font-size: 0.875rem; margin-left: 0.5rem;">{lesson['id']} (v{lesson['semver']})</span>
          </div>
          <div>
            <a href="/lessons/{slug}.md" style="font-size: 0.875rem;">📄 Raw Markdown</a>
          </div>
        </div>

        <h2 style="font-size: 1.5rem; margin-bottom: 1rem;">{html.escape(lesson.get('summary', ''))}</h2>

        <h3 style="font-size: 1rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem;">Verbatim Symptoms (Primary Search Key)</h3>
        <ul class="symptoms-list">
    """
    for s in lesson.get("symptoms", []):
        body += f"<li>{html.escape(s)}</li>\n"
    body += "</ul>\n"

    body += f"""
        <h3 style="font-size: 1.1rem; color: #fff; margin-top: 1.5rem; margin-bottom: 0.5rem;">Problem Statement</h3>
        <p style="margin-bottom: 1.5rem; color: var(--text);">{html.escape(lesson.get('problem', ''))}</p>

        <h3 style="font-size: 1.1rem; color: #fff; margin-top: 1.5rem; margin-bottom: 0.5rem;">Correct Procedure</h3>
        <ol style="margin-bottom: 1.5rem;">
    """
    for step in lesson.get("procedure", []):
        body += f"<li>{html.escape(step)}</li>\n"
    body += "</ol>\n"

    if lesson.get("anti_patterns"):
        body += "<h3 style=\"font-size: 1.1rem; color: #fff; margin-top: 1.5rem; margin-bottom: 0.5rem;\">Anti-Patterns</h3>\n<ul>\n"
        for ap in lesson.get("anti_patterns", []):
            body += f"<li>{html.escape(ap)}</li>\n"
        body += "</ul>\n"

    if lesson.get("failed_attempts"):
        body += "<h3 style=\"font-size: 1.1rem; color: #fff; margin-top: 1.5rem; margin-bottom: 0.5rem;\">Documented Dead Ends</h3>\n<ul>\n"
        for fa in lesson.get("failed_attempts", []):
            body += f"<li><strong>{html.escape(fa.get('approach', ''))}:</strong> {html.escape(fa.get('why_it_fails', ''))} <em>(~{fa.get('time_wasted_estimate_min', 0)} mins wasted)</em></li>\n"
        body += "</ul>\n"

    v = lesson.get("verification", {})
    body += f"""
        <div class="meta-grid">
          <div><strong>Docker Image:</strong> <code>{html.escape(v.get('image', ''))}</code></div>
          <div><strong>Networks:</strong> Setup: <code>{v.get('setup_network', 'packages')}</code> | Eval: <code>{v.get('network', 'none')}</code></div>
          <div><strong>Re-verify Cadence:</strong> Every {lesson.get('lifecycle', {}).get('reverify_cadence_days', 30)} days</div>
          <div><strong>Taint Level:</strong> <code>{lesson.get('provenance', {}).get('taint_level', 'clean')}</code></div>
        </div>
      </div>
    </main>
    """

    body += render_html_footer()
    return body


def generate_index_html(lessons: list[dict[str, Any]]) -> str:
    title = "Lore — Verified Experience Commons for AI Agents"
    desc = "Browse verified procedural knowledge artifacts for AI agents."

    body = render_html_header(title, desc)
    body += f"""
    <main>
      <div style="margin-bottom: 2rem;">
        <h2 style="font-size: 1.5rem; margin-bottom: 0.5rem;">Verified Lessons Corpus ({len(lessons)})</h2>
        <p style="color: var(--text-muted);">Every lesson below has executed its positive and negative eval in hard-capped Docker sandboxes.</p>
      </div>
    """

    for lesson in lessons:
        slug = lesson["_slug"]
        status = lesson.get("lifecycle", {}).get("status", "draft")
        badge_class = "badge-verified" if status == "verified" else "badge-draft"

        body += f"""
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.5rem;">
          <div>
            <span class="badge {badge_class}">{status}</span>
            <span style="color: var(--text-muted); font-size: 0.875rem; margin-left: 0.5rem;">{lesson['domain']} • v{lesson['semver']}</span>
          </div>
          <a href="/lessons/{slug}.html" style="font-weight: 600;">View Lesson →</a>
        </div>
        <h3 style="font-size: 1.125rem; margin-bottom: 0.5rem;"><a href="/lessons/{slug}.html" style="color: #fff;">{html.escape(lesson.get('summary', ''))}</a></h3>
        <ul class="symptoms-list" style="margin-bottom: 0;">
        """
        for s in lesson.get("symptoms", [])[:2]:  # show first 2
            body += f"<li>{html.escape(s)}</li>\n"
        body += "</ul>\n</div>\n"

    body += "</main>\n"
    body += render_html_footer()
    return body


def generate_llms_txt(lessons: list[dict[str, Any]]) -> str:
    lines = [
        "# Lore Commons — Verified Procedural Knowledge Index for LLMs",
        "",
        "> Lore is a global open registry of verified procedural knowledge artifacts.",
        "> Each lesson contains verbatim error symptoms, actionable procedures, documented dead ends,",
        "> and executable container evals that prove its claim.",
        "",
        "## Verified Lessons",
        "",
    ]
    for lesson in lessons:
        slug = lesson["_slug"]
        summary = lesson.get("summary", "")
        domain = lesson.get("domain", "")
        lines.append(f"- [{slug}]({SITE_DOMAIN}/lessons/{slug}.md): {summary} (domain: {domain})")
    lines.append("")
    return "\n".join(lines)


def generate_llms_full_txt(lessons: list[dict[str, Any]]) -> str:
    parts = [
        "# Lore Commons — Full Verified Corpus",
        "# Concatenated text of all verified lessons for LLM context windows.",
        "=" * 80,
        "",
    ]
    for lesson in lessons:
        parts.append(generate_lesson_markdown(lesson))
        parts.append("\n" + "=" * 80 + "\n")
    return "\n".join(parts)


def generate_sitemap_xml(lessons: list[dict[str, Any]]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '  <url>',
        f'    <loc>{SITE_DOMAIN}/</loc>',
        f'    <lastmod>{now}</lastmod>',
        '    <changefreq>daily</changefreq>',
        '    <priority>1.0</priority>',
        '  </url>',
        '  <url>',
        f'    <loc>{SITE_DOMAIN}/llms.txt</loc>',
        f'    <lastmod>{now}</lastmod>',
        '    <changefreq>daily</changefreq>',
        '    <priority>0.9</priority>',
        '  </url>',
    ]

    for lesson in lessons:
        slug = lesson["_slug"]
        lastmod = lesson.get("lifecycle", {}).get("last_verified", now)[:10]
        lines.extend([
            '  <url>',
            f'    <loc>{SITE_DOMAIN}/lessons/{slug}.html</loc>',
            f'    <lastmod>{lastmod}</lastmod>',
            '    <changefreq>weekly</changefreq>',
            '    <priority>0.8</priority>',
            '  </url>',
            '  <url>',
            f'    <loc>{SITE_DOMAIN}/lessons/{slug}.md</loc>',
            f'    <lastmod>{lastmod}</lastmod>',
            '    <changefreq>weekly</changefreq>',
            '    <priority>0.8</priority>',
            '  </url>',
        ])

    lines.append('</urlset>')
    return "\n".join(lines)


def build_site():
    repo_root = Path(__file__).parent.parent
    dist_dir = repo_root / "site" / "dist"
    public_dir = repo_root / "site" / "public"
    lessons_dist_dir = dist_dir / "lessons"

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)
    lessons_dist_dir.mkdir(parents=True, exist_ok=True)

    lessons = load_lessons(repo_root)
    print(f"Loaded {len(lessons)} lessons for static site generation...")

    # Index HTML
    (dist_dir / "index.html").write_text(generate_index_html(lessons), encoding="utf-8")

    # Lesson HTML & MD pages
    for lesson in lessons:
        slug = lesson["_slug"]
        (lessons_dist_dir / f"{slug}.html").write_text(generate_lesson_html(lesson), encoding="utf-8")
        (lessons_dist_dir / f"{slug}.md").write_text(generate_lesson_markdown(lesson), encoding="utf-8")

    # LLM Stack
    (dist_dir / "llms.txt").write_text(generate_llms_txt(lessons), encoding="utf-8")
    (dist_dir / "llms-full.txt").write_text(generate_llms_full_txt(lessons), encoding="utf-8")

    # Sitemap
    (dist_dir / "sitemap.xml").write_text(generate_sitemap_xml(lessons), encoding="utf-8")

    # Robots.txt
    if (public_dir / "robots.txt").exists():
        shutil.copy(public_dir / "robots.txt", dist_dir / "robots.txt")

    print(f"✅ Static site build complete! Artifacts written to {dist_dir}")


if __name__ == "__main__":
    build_site()
