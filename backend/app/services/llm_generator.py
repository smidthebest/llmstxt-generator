import hashlib
import json
import logging
import re
import time
from openai import AsyncOpenAI

from app.config import settings
from app.models.page import Page
from app.models.site import Site

logger = logging.getLogger(__name__)

# Hard cap on total pages in the final llms.txt (sections + optional combined).
# Safety net in case the LLM ignores the "20 pages max" instruction.
MAX_OUTPUT_PAGES = 30

# Titles that indicate junk pages (case-insensitive match)
_JUNK_TITLE_PATTERNS = [
    # Error / auth pages
    re.compile(r"^page\s*not\s*found$", re.IGNORECASE),
    re.compile(r"^404\b", re.IGNORECASE),
    re.compile(r"^not\s*found$", re.IGNORECASE),
    re.compile(r"^error\b", re.IGNORECASE),
    re.compile(r"^access\s*denied$", re.IGNORECASE),
    re.compile(r"^reset\s*password", re.IGNORECASE),
    re.compile(r"^log\s*in$", re.IGNORECASE),
    re.compile(r"^sign\s*(in|up)$", re.IGNORECASE),
    # Wiki-style namespace pages (Talk, Template, Category, etc.)
    re.compile(r"^Talk:", re.IGNORECASE),
    re.compile(r"^.+\s+talk:", re.IGNORECASE),  # "Template talk:", "User talk:", etc.
    re.compile(r"^Template:", re.IGNORECASE),
    re.compile(r"^Category:", re.IGNORECASE),
    re.compile(r"^Module:", re.IGNORECASE),
    re.compile(r"^Draft:", re.IGNORECASE),
    re.compile(r"^Special:", re.IGNORECASE),
    re.compile(r"^User:", re.IGNORECASE),
    re.compile(r"^File:", re.IGNORECASE),
    re.compile(r"^MediaWiki:", re.IGNORECASE),
    # Archive pages
    re.compile(r"[/:]Archive\s*\d+", re.IGNORECASE),
    # Pure year pages ("1600", "2006") and date pages ("February 19")
    re.compile(r"^\d{4}$"),
    re.compile(
        r"^(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2}$",
        re.IGNORECASE,
    ),
]


def _is_junk_title(title: str) -> bool:
    return any(p.search(title.strip()) for p in _JUNK_TITLE_PATTERNS)


def _clean_pages_for_llm(site: Site, pages: list[Page]) -> list[Page]:
    """Pre-filter pages before sending to the LLM.

    Removes junk and deduplicates so the LLM only sees unique, valuable pages.
    """
    # Pass 1: Remove junk pages and deduplicate by URL
    seen_urls: set[str] = set()
    filtered: list[Page] = []
    for p in pages:
        if p.url in seen_urls:
            continue
        seen_urls.add(p.url)

        title = (p.title or "").strip()

        # Skip pages with junk titles
        if _is_junk_title(title):
            continue

        # Skip pages with no title at all
        if not title:
            continue

        filtered.append(p)

    # Pass 2: Deduplicate by title — keep only the best page per unique title.
    # SPAs often return dozens of URLs that all render with the site's default
    # title (e.g. "Resy | Right This Way") because the page didn't hydrate
    # unique content.
    title_best: dict[str, Page] = {}
    for p in filtered:
        key = (p.title or "").strip().lower()
        existing = title_best.get(key)
        if existing is None or p.relevance_score > existing.relevance_score:
            title_best[key] = p

    deduped = list(title_best.values())

    removed = len(pages) - len(deduped)
    if removed > 0:
        logger.info(
            "%s: pre-filter removed %d/%d junk/duplicate pages before LLM",
            site.domain, removed, len(pages),
        )

    return deduped


SYSTEM_PROMPT = """You organize website pages into a concise llms.txt that helps LLMs understand what a site offers.

You receive a list of pages (ID + title). Output a JSON object selecting ONLY the most important pages.

HARD LIMIT: Pick at most 20 pages total (sections + optional combined). Quality over quantity — a 10-page llms.txt is better than a 50-page one. Omit any page ID you don't select.

Output format (strict JSON):
{
  "site_description": "2-3 sentences: what this site is and what it offers",
  "sections": [
    {"name": "Section Name", "pages": [{"id": 1, "title": "Clean Title", "description": "One sentence"}]}
  ],
  "optional": [{"id": 12, "title": "Title", "description": "Brief description"}]
}

Rules:
1. Be RUTHLESS. Only include pages that help someone understand what this site does and its key content areas.
2. EXCLUDE: admin/meta pages, discussion pages, help/tutorial pages, navigation indexes, archive pages, date/year listings, random individual content items (e.g. individual Wikipedia articles, individual blog posts, individual product pages). Focus on structural pages that explain the site.
3. Sections should reflect the site's structure. 2-5 sections max.
4. Optional: at most 5 low-priority but genuinely useful pages.
5. Write a UNIQUE description for each page — do not repeat the site description.
6. Clean titles: strip site name suffixes, pipes, branding."""


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

    Returns (content, content_hash, site_description).
    """

    client = AsyncOpenAI(api_key=settings.llmstxt_openai_key)

    # Aggressive pre-filter: remove junk, dedup by URL and title
    clean = _clean_pages_for_llm(site, pages)

    # Sort by relevance (descending), then depth (ascending) for tie-breaking.
    # Send ALL cleaned pages to the LLM — let it decide what's important.
    llm_pages = sorted(clean, key=lambda x: (-x.relevance_score, x.depth, x.url))

    logger.info("%s: sending all %d cleaned pages to LLM", site.domain, len(llm_pages))

    # Build page index: ID -> Page, and the prompt listing.
    # Only send title (and description if it's unique / non-default).
    page_index: dict[int, Page] = {}
    page_lines = []
    site_desc_norm = (site.description or "").strip().lower()
    for i, p in enumerate(sorted(llm_pages, key=lambda x: (x.depth, x.url))):
        page_id = i + 1
        page_index[page_id] = p
        title = p.title or "(no title)"
        # Only include description if it exists AND is meaningfully different
        # from the title (many SPA pages repeat title as description)
        desc = p.description or ""
        if site_desc_norm and desc.strip().lower() == site_desc_norm:
            desc = ""
        if desc and desc.strip().lower() != title.strip().lower():
            if len(desc) > 150:
                desc = desc[:150] + "..."
            page_lines.append(f"[{page_id}] {title} — {desc}")
        else:
            page_lines.append(f"[{page_id}] {title}")

    pages_text = "\n".join(page_lines)

    user_prompt = f"""Organize these {len(llm_pages)} pages from {site.title or site.domain} ({site.url}):

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
        content = _assemble_from_plan(site, page_index, plan)
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
) -> str:
    """Build llms.txt Markdown from the LLM's JSON plan + our real page data."""
    lines: list[str] = []
    seen_urls: set[str] = set()
    total_pages = 0

    # Header — strip tagline suffixes like "Site - Tagline" or "Site | Motto"
    raw_title = site.title or site.domain
    for sep in (" - ", " | ", " — ", " · ", " : "):
        if sep in raw_title:
            raw_title = raw_title.split(sep, 1)[0]
            break
    lines.append(f"# {raw_title.strip()}")
    site_desc = plan.get("site_description") or site.description
    if site_desc:
        lines.append(f"\n> {site_desc}")
    lines.append("")

    # Sections from LLM plan
    for section in plan.get("sections", []):
        section_name = section.get("name", "Other")
        section_pages = section.get("pages", [])
        if not section_pages:
            continue

        section_lines: list[str] = []
        for entry in section_pages:
            if total_pages >= MAX_OUTPUT_PAGES:
                break
            page_id = entry.get("id")
            page = page_index.get(page_id)
            if not page or page.url in seen_urls:
                continue

            seen_urls.add(page.url)
            entry_title = entry.get("title") or page.title or page.url
            entry_desc = entry.get("description") or page.description
            section_lines.append(_format_md_link(entry_title, page.url, entry_desc))
            total_pages += 1

        if section_lines:
            lines.append(f"## {section_name}")
            lines.append("")
            lines.extend(section_lines)
            lines.append("")

    # Optional section from LLM plan
    optional_entries = plan.get("optional", [])
    optional_lines: list[str] = []
    for entry in optional_entries:
        if total_pages >= MAX_OUTPUT_PAGES:
            break
        page_id = entry.get("id")
        page = page_index.get(page_id)
        if not page or page.url in seen_urls:
            continue

        seen_urls.add(page.url)
        entry_title = entry.get("title") or page.title or page.url
        entry_desc = entry.get("description") or page.description
        optional_lines.append(_format_md_link(entry_title, page.url, entry_desc))
        total_pages += 1

    if optional_lines:
        lines.append("## Optional")
        lines.append("")
        lines.extend(optional_lines)
        lines.append("")

    logger.info("Assembled llms.txt with %d pages (cap=%d)", total_pages, MAX_OUTPUT_PAGES)
    return "\n".join(lines)
