import hashlib
import json
import logging
import re
from urllib.parse import quote

from openai import AsyncOpenAI

from app.config import settings
from app.models.page import Page
from app.models.site import Site

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert at organizing website pages into a structured llms.txt file.

You will receive a numbered list of pages crawled from a website. Each page has an ID, title, description, and depth.

Your job is to output a JSON object that organizes these pages into logical sections. You decide:
- What sections to create and what to name them
- Which pages go in which section (by their ID number)
- A clean, concise description for each page (rewrite if the original is messy)
- Which pages are low-value and should go in the "Optional" section
- Which pages to EXCLUDE entirely (duplicates, versioned copies, junk pages)

Output format (strict JSON, no markdown, no explanation):
{
  "site_description": "A one-line description of this website",
  "sections": [
    {
      "name": "Section Name",
      "pages": [
        {"id": 1, "title": "Clean Page Title", "description": "Concise description"},
        {"id": 5, "title": "Another Page", "description": "What this page covers"}
      ]
    }
  ],
  "optional": [
    {"id": 12, "title": "Less Important Page", "description": "Why this exists"}
  ]
}

Rules:
1. Sections should reflect the ACTUAL content structure of this specific site
2. Order sections from most important to least important
3. Deduplicate: if multiple pages cover the same content (e.g. versioned docs), include only the canonical/latest one
4. Exclude truly useless pages (navigation-only, error pages, meta pages)
5. Keep descriptions under 100 characters
6. Use clean, readable titles (strip " - Wikipedia", " | Docs", etc. suffixes if redundant)
7. Output ONLY valid JSON, nothing else"""


async def generate_llms_txt_with_llm(site: Site, pages: list[Page]) -> tuple[str, str]:
    """Use an LLM to organize pages, then construct llms.txt with guaranteed-correct URLs."""

    client = AsyncOpenAI(api_key=settings.llmstxt_openai_key)

    # Build page index: ID -> Page, and the prompt listing
    page_index: dict[int, Page] = {}
    page_lines = []
    for i, p in enumerate(sorted(pages, key=lambda x: (x.depth, x.url))):
        page_id = i + 1
        page_index[page_id] = p
        title = p.title or "(no title)"
        desc = p.description or "(no description)"
        if len(desc) > 200:
            desc = desc[:200] + "..."
        page_lines.append(f"[{page_id}] Title: {title} | Description: {desc} | Depth: {p.depth}")

    pages_text = "\n".join(page_lines)

    user_prompt = f"""Organize these pages from {site.title or site.domain} ({site.url}) into a structured llms.txt.

{len(pages)} crawled pages:

{pages_text}

Output the JSON structure now."""

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_completion_tokens=4096,
        )

        raw = response.choices[0].message.content.strip()

        # Strip code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            raw = "\n".join(lines)

        plan = json.loads(raw)

        # Assemble llms.txt from the plan using REAL URLs from our database
        content = _assemble_from_plan(site, page_index, plan)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        logger.info(f"LLM generated llms.txt for {site.domain} ({len(content)} chars)")
        return content, content_hash

    except Exception as e:
        logger.exception(f"LLM generation failed for {site.domain}, falling back to deterministic")
        from app.services.generator import generate_llms_txt
        return generate_llms_txt(site, pages)


def _format_md_link(title: str, url: str, description: str | None) -> str:
    """Format a Markdown link entry, properly escaping URLs with parentheses."""
    # Markdown links break if the URL contains unescaped parentheses
    safe_url = url.replace("(", "%28").replace(")", "%29")
    desc_part = f": {description}" if description else ""
    return f"- [{title}]({safe_url}){desc_part}"


def _assemble_from_plan(
    site: Site, page_index: dict[int, Page], plan: dict
) -> str:
    """Build llms.txt Markdown from the LLM's JSON plan + our real page data."""
    lines: list[str] = []

    # Header
    title = site.title or site.domain
    lines.append(f"# {title}")
    site_desc = plan.get("site_description") or site.description
    if site_desc:
        lines.append(f"\n> {site_desc}")
    lines.append("")

    # Sections
    for section in plan.get("sections", []):
        section_name = section.get("name", "Other")
        section_pages = section.get("pages", [])
        if not section_pages:
            continue

        lines.append(f"## {section_name}")
        lines.append("")
        for entry in section_pages:
            page_id = entry.get("id")
            page = page_index.get(page_id)
            if not page:
                continue  # Skip if LLM referenced a non-existent ID

            # Use LLM's cleaned title/description, but OUR real URL
            entry_title = entry.get("title") or page.title or page.url
            entry_desc = entry.get("description") or page.description
            lines.append(_format_md_link(entry_title, page.url, entry_desc))
        lines.append("")

    # Optional section
    optional_pages = plan.get("optional", [])
    if optional_pages:
        lines.append("## Optional")
        lines.append("")
        for entry in optional_pages:
            page_id = entry.get("id")
            page = page_index.get(page_id)
            if not page:
                continue

            entry_title = entry.get("title") or page.title or page.url
            entry_desc = entry.get("description") or page.description
            lines.append(_format_md_link(entry_title, page.url, entry_desc))
        lines.append("")

    return "\n".join(lines)
