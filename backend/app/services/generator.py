import hashlib

from app.models.page import Page
from app.models.site import Site

SECTION_ORDER = [
    "Getting Started",
    "Documentation",
    "API Reference",
    "Guides",
    "Examples",
    "Core Pages",
    "FAQ",
    "Changelog",
    "About",
    "Blog",
    "Other",
]

OPTIONAL_THRESHOLD = 0.3


def generate_llms_txt(site: Site, pages: list[Page]) -> tuple[str, str]:
    """Generate llms.txt content and return (content, content_hash)."""
    lines: list[str] = []
    seen_urls: set[str] = set()

    # Header
    title = site.title or site.domain
    lines.append(f"# {title}")
    if site.description:
        lines.append(f"\n> {site.description}")
    lines.append("")

    # Group pages by category
    categorized: dict[str, list[Page]] = {}
    optional_pages: list[Page] = []

    for page in sorted(pages, key=lambda p: -p.relevance_score):
        if page.url in seen_urls:
            continue
        seen_urls.add(page.url)
        if page.relevance_score < OPTIONAL_THRESHOLD:
            optional_pages.append(page)
        else:
            categorized.setdefault(page.category, []).append(page)

    # Emit sections in order
    for section in SECTION_ORDER:
        section_pages = categorized.get(section, [])
        if not section_pages:
            continue
        lines.append(f"## {section}")
        lines.append("")
        for page in section_pages:
            desc = f": {page.description}" if page.description else ""
            label = page.title or page.url
            safe_url = page.url.replace("(", "%28").replace(")", "%29")
            lines.append(f"- [{label}]({safe_url}){desc}")
        lines.append("")

    # Optional section
    if optional_pages:
        lines.append("## Optional")
        lines.append("")
        for page in optional_pages:
            desc = f": {page.description}" if page.description else ""
            label = page.title or page.url
            safe_url = page.url.replace("(", "%28").replace(")", "%29")
            lines.append(f"- [{label}]({safe_url}){desc}")
        lines.append("")

    content = "\n".join(lines)
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return content, content_hash
