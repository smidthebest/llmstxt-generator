import hashlib
import json
import logging
import time
from collections import defaultdict

from openai import AsyncOpenAI

from app.config import settings
from app.models.page import Page
from app.models.site import Site

logger = logging.getLogger(__name__)

# Max pages to send to LLM for intelligent organization.
# Pages beyond this are grouped by their pre-assigned category.
LLM_PAGE_CAP = 150

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
  "site_description": "A thorough description of this website",
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
5. Use clean, readable titles (strip " - Wikipedia", " | Docs", etc. suffixes if redundant)"""


RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "llmstxt_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "required": ["site_description", "sections", "optional"],
            "additionalProperties": False,
            "properties": {
                "site_description": {
                    "type": "string",
                    "description": "A thorough summary of what this website is about",
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "pages"],
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "pages": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["id", "title", "description"],
                                    "additionalProperties": False,
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "optional": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "title", "description"],
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "integer"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


async def generate_llms_txt_with_llm(site: Site, pages: list[Page]) -> tuple[str, str, str]:
    """Use an LLM to organize pages, then construct llms.txt with guaranteed-correct URLs.

    If there are more than LLM_PAGE_CAP pages, only the top pages (by relevance)
    are sent to the LLM. The rest are grouped by their pre-assigned category and
    appended as additional sections. This keeps LLM latency under ~20s even for
    500-page crawls.

    Returns (content, content_hash, site_description).
    """

    client = AsyncOpenAI(api_key=settings.llmstxt_openai_key)

    # Sort by relevance (descending), then depth (ascending) for tie-breaking
    sorted_pages = sorted(pages, key=lambda x: (-x.relevance_score, x.depth, x.url))

    # Split into LLM-organized and overflow pages
    llm_pages = sorted_pages[:LLM_PAGE_CAP]
    overflow_pages = sorted_pages[LLM_PAGE_CAP:]

    if overflow_pages:
        logger.info(
            "%s: sending %d/%d pages to LLM, %d overflow pages grouped by category",
            site.domain, len(llm_pages), len(pages), len(overflow_pages),
        )

    # Build page index: ID -> Page, and the prompt listing
    page_index: dict[int, Page] = {}
    page_lines = []
    for i, p in enumerate(sorted(llm_pages, key=lambda x: (x.depth, x.url))):
        page_id = i + 1
        page_index[page_id] = p
        title = p.title or "(no title)"
        desc = p.description or "(no description)"
        if len(desc) > 200:
            desc = desc[:200] + "..."
        page_lines.append(f"[{page_id}] Title: {title} | Description: {desc} | Depth: {p.depth}")

    pages_text = "\n".join(page_lines)

    user_prompt = f"""Organize these pages from {site.title or site.domain} ({site.url}) into a structured llms.txt.

{len(llm_pages)} crawled pages:

{pages_text}"""

    try:
        t0 = time.monotonic()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_completion_tokens=16384,
            response_format=RESPONSE_SCHEMA,
        )
        t1 = time.monotonic()

        choice = response.choices[0]
        usage = response.usage
        logger.info(
            "LLM API call for %s: %.1fs, %d input tokens, %d output tokens",
            site.domain, t1 - t0,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )

        if choice.finish_reason == "length":
            raise ValueError("LLM response truncated — too many pages for token limit")
        raw = choice.message.content or ""
        if not raw.strip():
            raise ValueError("LLM returned empty content")
        plan = json.loads(raw.strip())

        # Assemble llms.txt from the plan using REAL URLs from our database
        content = _assemble_from_plan(site, page_index, plan, overflow_pages)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        site_description = plan.get("site_description", "")
        logger.info("LLM generated llms.txt for %s (%d chars)", site.domain, len(content))
        return content, content_hash, site_description

    except Exception as e:
        logger.exception("LLM generation failed for %s, falling back to deterministic", site.domain)
        from app.services.generator import generate_llms_txt
        content, content_hash = generate_llms_txt(site, pages)
        return content, content_hash, ""


def _format_md_link(title: str, url: str, description: str | None) -> str:
    """Format a Markdown link entry, properly escaping URLs with parentheses."""
    # Markdown links break if the URL contains unescaped parentheses
    safe_url = url.replace("(", "%28").replace(")", "%29")
    desc_part = f": {description}" if description else ""
    return f"- [{title}]({safe_url}){desc_part}"


def _assemble_from_plan(
    site: Site, page_index: dict[int, Page], plan: dict,
    overflow_pages: list[Page] | None = None,
) -> str:
    """Build llms.txt Markdown from the LLM's JSON plan + our real page data.

    If overflow_pages is provided, they are appended as additional sections
    grouped by their pre-assigned category (from the categorizer).
    """
    lines: list[str] = []

    # Header
    title = site.title or site.domain
    lines.append(f"# {title}")
    site_desc = plan.get("site_description") or site.description
    if site_desc:
        lines.append(f"\n> {site_desc}")
    lines.append("")

    # Track which section names the LLM used (for dedup with overflow)
    llm_section_names: set[str] = set()

    # Sections from LLM plan
    for section in plan.get("sections", []):
        section_name = section.get("name", "Other")
        section_pages = section.get("pages", [])
        if not section_pages:
            continue

        llm_section_names.add(section_name.lower())
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

    # Optional section from LLM plan
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

    # Append overflow pages grouped by category
    if overflow_pages:
        by_category: dict[str, list[Page]] = defaultdict(list)
        for p in overflow_pages:
            cat = p.category or "Other"
            by_category[cat].append(p)

        for cat_name in sorted(by_category.keys()):
            cat_pages = by_category[cat_name]
            # If LLM already created a similar section, prefix with "More"
            display_name = cat_name
            if cat_name.lower() in llm_section_names:
                display_name = f"More {cat_name}"
            lines.append(f"## {display_name}")
            lines.append("")
            for p in sorted(cat_pages, key=lambda x: (-x.relevance_score, x.url)):
                p_title = p.title or p.url
                p_desc = p.description
                lines.append(_format_md_link(p_title, p.url, p_desc))
            lines.append("")

    return "\n".join(lines)
