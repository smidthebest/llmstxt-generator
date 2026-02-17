import hashlib
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class PageMetadata:
    url: str
    title: str | None
    description: str | None
    content_hash: str
    metadata_hash: str
    headings_hash: str
    text_hash: str
    links: list[str]
    canonical_url: str | None
    etag: str | None = None
    last_modified: str | None = None
    http_status: int = 200
    not_modified: bool = False


def extract_metadata(
    url: str,
    html: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    http_status: int = 200,
) -> PageMetadata:
    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup)
    description = _extract_description(soup)
    headings = _extract_headings(soup)
    main_text = _extract_main_text(soup)
    links = _extract_links(soup, url)
    canonical_url = _extract_canonical_url(soup, url)

    metadata_hash = hashlib.sha256(f"{title or ''}{description or ''}".encode()).hexdigest()
    headings_hash = hashlib.sha256("||".join(headings).encode()).hexdigest()
    text_hash = hashlib.sha256(main_text.encode()).hexdigest()
    hash_input = f"{metadata_hash}{headings_hash}{text_hash}"
    content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    return PageMetadata(
        url=url,
        title=title,
        description=description,
        content_hash=content_hash,
        metadata_hash=metadata_hash,
        headings_hash=headings_hash,
        text_hash=text_hash,
        links=links,
        canonical_url=canonical_url,
        etag=etag,
        last_modified=last_modified,
        http_status=http_status,
    )


def _extract_title(soup: BeautifulSoup) -> str | None:
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return None


def _extract_description(soup: BeautifulSoup) -> str | None:
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        return og_desc["content"].strip()
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        return meta_desc["content"].strip()
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) >= 50:
            return text[:300]
    return None


def _extract_headings(soup: BeautifulSoup) -> list[str]:
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(strip=True)
        if text:
            headings.append(text)
    return headings[:20]


def _extract_main_text(soup: BeautifulSoup) -> str:
    # Remove non-content tags that create volatile noise in diffing.
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()

    candidate = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
        or soup
    )

    chunks: list[str] = []
    for tag in candidate.find_all(["h1", "h2", "h3", "p", "li", "pre", "code", "td"]):
        text = tag.get_text(" ", strip=True)
        if text:
            chunks.append(text)

    if not chunks:
        raw = candidate.get_text(" ", strip=True)
    else:
        raw = " ".join(chunks)

    normalized = re.sub(r"\s+", " ", raw).strip().lower()
    return normalized[:50000]


def _extract_canonical_url(soup: BeautifulSoup, base_url: str) -> str | None:
    from urllib.parse import urljoin, urlparse

    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    if not canonical or not canonical.get("href"):
        return None

    absolute = urljoin(base_url, canonical["href"])
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    from urllib.parse import urljoin, urlparse

    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        clean = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
        if clean in seen:
            continue
        seen.add(clean)
        links.append(clean)
    return links
