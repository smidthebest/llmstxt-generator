import hashlib
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class PageMetadata:
    url: str
    title: str | None
    description: str | None
    content_hash: str
    links: list[str]


def extract_metadata(url: str, html: str) -> PageMetadata:
    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup)
    description = _extract_description(soup)
    headings = _extract_headings(soup)
    links = _extract_links(soup, url)

    hash_input = f"{title or ''}{description or ''}{''.join(headings)}"
    content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    return PageMetadata(
        url=url,
        title=title,
        description=description,
        content_hash=content_hash,
        links=links,
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


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    from urllib.parse import urljoin, urlparse

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean.endswith("/"):
            clean = clean.rstrip("/") or clean
        links.append(clean)
    return links
