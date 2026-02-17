import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from robotexclusionrulesparser import RobotExclusionRulesParser

from app.config import settings
from app.services.extractor import PageMetadata, extract_metadata

logger = logging.getLogger(__name__)

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mp3", ".wav",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
}


@dataclass
class ExistingPageState:
    title: str | None
    description: str | None
    content_hash: str | None
    metadata_hash: str | None
    headings_hash: str | None
    text_hash: str | None
    links: list[str]
    canonical_url: str | None
    etag: str | None
    last_modified: str | None


class Crawler:
    def __init__(
        self,
        root_url: str,
        max_depth: int = settings.max_crawl_depth,
        max_pages: int = settings.max_crawl_pages,
        concurrency: int = settings.crawl_concurrency,
        delay_ms: int = settings.crawl_delay_ms,
        existing_page_state: dict[str, ExistingPageState] | None = None,
        on_page_crawled=None,
        on_page_skipped=None,
    ):
        self.root_url = self._normalize_url(root_url)
        parsed = urlparse(self.root_url)
        self.domain = parsed.netloc
        self.scheme = parsed.scheme
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.semaphore = asyncio.Semaphore(concurrency)
        self.delay = delay_ms / 1000.0
        self.existing_page_state = existing_page_state or {}
        self.on_page_crawled = on_page_crawled
        self.on_page_skipped = on_page_skipped

        self.visited: set[str] = set()
        self.results: list[tuple[PageMetadata, int]] = []  # (metadata, depth)
        self.skipped: int = 0
        self.robot_parser: RobotExclusionRulesParser | None = None

    async def crawl(self) -> list[tuple[PageMetadata, int]]:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "LlmsTxtGenerator/1.0"},
        ) as client:
            self.client = client
            await self._load_robots()
            sitemap_urls = await self._load_sitemap()

            queue: deque[tuple[str, int]] = deque()
            queue.append((self.root_url, 0))
            for url in sitemap_urls:
                if url not in self.visited:
                    queue.append((url, 1))

            while queue and len(self.results) < self.max_pages:
                url, depth = queue.popleft()
                url = self._normalize_url(url)
                if url in self.visited or depth > self.max_depth:
                    continue
                self.visited.add(url)

                metadata, skip_reason = await self._fetch_page(url)
                if metadata is None:
                    if skip_reason and self.on_page_skipped:
                        self.skipped += 1
                        await self.on_page_skipped(url, depth, skip_reason, self.skipped)
                    continue

                if metadata.url not in self.visited:
                    self.visited.add(metadata.url)
                self.results.append((metadata, depth))
                if self.on_page_crawled:
                    await self.on_page_crawled(metadata, depth, len(self.results), len(self.visited))

                if depth < self.max_depth:
                    for link in metadata.links:
                        if self._should_crawl(link) and link not in self.visited:
                            queue.append((link, depth + 1))

        return self.results

    async def _fetch_page(self, url: str) -> tuple[PageMetadata | None, str | None]:
        async with self.semaphore:
            try:
                await asyncio.sleep(self.delay)
                headers = {}
                existing = self.existing_page_state.get(url)
                if existing and existing.etag:
                    headers["If-None-Match"] = existing.etag
                if existing and existing.last_modified:
                    headers["If-Modified-Since"] = existing.last_modified

                resp = await self.client.get(url, headers=headers)

                if resp.status_code == 304:
                    if not existing:
                        return None, "HTTP 304 without cached page state"
                    return (
                        PageMetadata(
                            url=url,
                            title=existing.title,
                            description=existing.description,
                            content_hash=existing.content_hash or "",
                            metadata_hash=existing.metadata_hash or "",
                            headings_hash=existing.headings_hash or "",
                            text_hash=existing.text_hash or "",
                            links=existing.links,
                            canonical_url=existing.canonical_url,
                            etag=existing.etag,
                            last_modified=existing.last_modified,
                            http_status=304,
                            not_modified=True,
                        ),
                        None,
                    )

                if resp.status_code != 200:
                    return None, f"HTTP {resp.status_code}"
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return None, f"Non-HTML ({content_type.split(';')[0].strip()})"

                final_url = self._normalize_url(str(resp.url))
                metadata = extract_metadata(
                    final_url,
                    resp.text,
                    etag=resp.headers.get("etag"),
                    last_modified=resp.headers.get("last-modified"),
                    http_status=resp.status_code,
                )
                if metadata is None:
                    return None, "Empty or unparseable HTML"
                return metadata, None
            except httpx.TimeoutException:
                logger.warning("Timeout fetching %s", url)
                return None, "Timeout"
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", url, e)
                return None, str(e)[:100]

    def _should_crawl(self, url: str) -> bool:
        url = self._normalize_url(url)
        parsed = urlparse(url)
        if parsed.netloc != self.domain:
            return False
        if parsed.query:
            return False
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return False
        if any(seg in path for seg in ["/login", "/signin", "/signup", "/register", "/admin"]):
            return False
        if self.robot_parser and not self.robot_parser.is_allowed("*", url):
            return False
        return True

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return url
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"

    async def _load_robots(self):
        try:
            resp = await self.client.get(f"{self.scheme}://{self.domain}/robots.txt")
            if resp.status_code == 200:
                self.robot_parser = RobotExclusionRulesParser()
                self.robot_parser.parse(resp.text)
        except Exception:
            pass

    async def _load_sitemap(self) -> list[str]:
        urls = []
        try:
            resp = await self.client.get(f"{self.scheme}://{self.domain}/sitemap.xml")
            if resp.status_code == 200 and "xml" in resp.headers.get("content-type", ""):
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml-xml")
                for loc in soup.find_all("loc"):
                    url = self._normalize_url(loc.get_text(strip=True))
                    if self._should_crawl(url):
                        urls.append(url)
        except Exception:
            pass
        return urls[:self.max_pages]
