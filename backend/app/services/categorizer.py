import re
from urllib.parse import urlparse

CATEGORY_PATTERNS: list[tuple[str, str]] = [
    (r"/docs?(/|$)", "Documentation"),
    (r"/documentation(/|$)", "Documentation"),
    (r"/api(-ref|reference|docs)?(/|$)", "API Reference"),
    (r"/guide", "Guides"),
    (r"/tutorial", "Guides"),
    (r"/getting[_-]?started", "Getting Started"),
    (r"/quick[_-]?start", "Getting Started"),
    (r"/install", "Getting Started"),
    (r"/setup", "Getting Started"),
    (r"/blog(/|$)", "Blog"),
    (r"/news(/|$)", "Blog"),
    (r"/example", "Examples"),
    (r"/demo", "Examples"),
    (r"/sample", "Examples"),
    (r"/faq", "FAQ"),
    (r"/changelog", "Changelog"),
    (r"/release", "Changelog"),
    (r"/about", "About"),
    (r"/team", "About"),
    (r"/contact", "About"),
    (r"/pricing", "About"),
]

CATEGORY_BASE_SCORES = {
    "Getting Started": 0.9,
    "Documentation": 0.85,
    "API Reference": 0.8,
    "Guides": 0.75,
    "Examples": 0.7,
    "Core Pages": 0.6,
    "FAQ": 0.5,
    "Changelog": 0.4,
    "About": 0.4,
    "Blog": 0.35,
    "Other": 0.25,
}


def categorize_page(url: str, depth: int) -> str:
    path = urlparse(url).path.lower()
    for pattern, category in CATEGORY_PATTERNS:
        if re.search(pattern, path):
            return category
    if depth <= 1:
        return "Core Pages"
    return "Other"


def compute_relevance(url: str, depth: int, category: str, in_sitemap: bool = False) -> float:
    base = CATEGORY_BASE_SCORES.get(category, 0.3)
    depth_penalty = depth * 0.1
    sitemap_bonus = 0.1 if in_sitemap else 0.0
    path_length = len(urlparse(url).path.split("/")) - 1
    length_penalty = max(0, (path_length - 3) * 0.05)

    score = base - depth_penalty + sitemap_bonus - length_penalty
    return max(0.0, min(1.0, round(score, 2)))
