import asyncio
import logging
from collections import deque
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


class Crawler:
    def __init__(
        self,
        root_url: str,
        max_depth: int = settings.max_crawl_depth,
        max_pages: int = settings.max_crawl_pages,
        concurrency: int = settings.crawl_concurrency,
        delay_ms: int = settings.crawl_delay_ms,
        on_page_crawled=None,
    ):
        self.root_url = root_url.rstrip("/")
        parsed = urlparse(self.root_url)
        self.domain = parsed.netloc
        self.scheme = parsed.scheme
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.semaphore = asyncio.Semaphore(concurrency)
        self.delay = delay_ms / 1000.0
        self.on_page_crawled = on_page_crawled

        self.visited: set[str] = set()
        self.results: list[tuple[PageMetadata, int]] = []  # (metadata, depth)
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
                if url in self.visited or depth > self.max_depth:
                    continue
                self.visited.add(url)

                metadata = await self._fetch_page(url)
                if metadata is None:
                    continue

                self.results.append((metadata, depth))
                if self.on_page_crawled:
                    await self.on_page_crawled(metadata, depth, len(self.results), len(self.visited))

                if depth < self.max_depth:
                    for link in metadata.links:
                        if self._should_crawl(link) and link not in self.visited:
                            queue.append((link, depth + 1))

        return self.results

    async def _fetch_page(self, url: str) -> PageMetadata | None:
        async with self.semaphore:
            try:
                await asyncio.sleep(self.delay)
                resp = await self.client.get(url)
                if resp.status_code != 200:
                    return None
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return None
                return extract_metadata(url, resp.text)
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                return None

    def _should_crawl(self, url: str) -> bool:
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
                    url = loc.get_text(strip=True)
                    if self._should_crawl(url):
                        urls.append(url)
        except Exception:
            pass
        return urls[:self.max_pages]
