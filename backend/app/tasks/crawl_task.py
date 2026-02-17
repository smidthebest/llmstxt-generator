import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CrawlJob, GeneratedFile, Page, Site
from app.services.categorizer import categorize_page, compute_relevance
from app.services.crawler import Crawler
from app.services.extractor import PageMetadata
from app.services.generator import generate_llms_txt

logger = logging.getLogger(__name__)


async def run_crawl_job(
    db: AsyncSession,
    site_id: int,
    crawl_job_id: int | None = None,
    max_depth: int | None = None,
    max_pages: int | None = None,
) -> bool:
    """Execute a full crawl + categorize + generate pipeline."""
    site = await db.get(Site, site_id)
    if not site:
        logger.error("Site %s not found", site_id)
        return False

    if crawl_job_id:
        job = await db.get(CrawlJob, crawl_job_id)
        if not job:
            logger.error("Crawl job %s not found", crawl_job_id)
            return False
    else:
        job = CrawlJob(site_id=site_id, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)

    job.status = "running"
    job.max_pages = max_pages if max_pages is not None else settings.max_crawl_pages
    await db.commit()

    try:
        # Get existing page hashes for change detection
        result = await db.execute(
            select(Page.url, Page.content_hash).where(Page.site_id == site_id)
        )
        old_hashes = {row.url: row.content_hash for row in result}

        # Delete old pages before inserting new ones incrementally
        old_pages = await db.execute(select(Page).where(Page.site_id == site_id))
        for page in old_pages.scalars():
            await db.delete(page)
        await db.commit()

        pages_changed = 0
        new_pages: list[Page] = []

        async def on_page_skipped(
            url: str, depth: int, reason: str, skipped_count: int
        ):
            job.pages_skipped = skipped_count
            await db.commit()

        async def on_page_crawled(
            metadata: PageMetadata, depth: int, crawled: int, found: int
        ):
            nonlocal pages_changed

            category = categorize_page(metadata.url, depth)
            relevance = compute_relevance(metadata.url, depth, category)

            old_hash = old_hashes.get(metadata.url)
            changed = (old_hash and old_hash != metadata.content_hash) or (not old_hash)
            if changed:
                pages_changed += 1

            page = Page(
                site_id=site_id,
                url=metadata.url,
                title=metadata.title,
                description=metadata.description,
                content_hash=metadata.content_hash,
                category=category,
                relevance_score=relevance,
                depth=depth,
            )
            db.add(page)
            new_pages.append(page)

            job.pages_crawled = crawled
            job.pages_found = found
            job.pages_changed = pages_changed
            await db.commit()

        crawler_kwargs: dict = {}
        if max_depth is not None:
            crawler_kwargs["max_depth"] = max_depth
        if max_pages is not None:
            crawler_kwargs["max_pages"] = max_pages

        crawler = Crawler(
            site.url,
            on_page_crawled=on_page_crawled,
            on_page_skipped=on_page_skipped,
            **crawler_kwargs,
        )
        crawl_results = await crawler.crawl()

        # Update site title/description from root page
        if crawl_results:
            root_meta: PageMetadata = crawl_results[0][0]
            if root_meta.title:
                site.title = root_meta.title
            if root_meta.description:
                site.description = root_meta.description

        job.pages_found = len(crawl_results)
        job.pages_crawled = len(crawl_results)
        job.pages_changed = pages_changed
        job.pages_skipped = crawler.skipped
        job.status = "completed"
        await db.commit()

        # Generate llms.txt
        if settings.llmstxt_openai_key:
            from app.services.llm_generator import generate_llms_txt_with_llm

            content, content_hash, site_desc = await generate_llms_txt_with_llm(
                site, new_pages
            )
            if site_desc:
                site.description = site_desc
        else:
            content, content_hash = generate_llms_txt(site, new_pages)

        generated = GeneratedFile(
            site_id=site_id,
            crawl_job_id=job.id,
            content=content,
            content_hash=content_hash,
        )
        db.add(generated)
        await db.commit()

        logger.info(
            "Crawl completed for %s: %s pages, %s changed, %s skipped",
            site.domain,
            len(crawl_results),
            pages_changed,
            crawler.skipped,
        )
        return True

    except Exception as exc:
        logger.exception("Crawl failed for site %s", site_id)
        job.status = "failed"
        job.error_message = str(exc)[:1024]
        await db.commit()
        return False
