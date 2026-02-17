from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CrawlJob(Base, TimestampMixin):
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/completed/failed
    pages_found: Mapped[int] = mapped_column(Integer, default=0)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    pages_changed: Mapped[int] = mapped_column(Integer, default=0)
    pages_added: Mapped[int] = mapped_column(Integer, default=0)
    pages_updated: Mapped[int] = mapped_column(Integer, default=0)
    pages_removed: Mapped[int] = mapped_column(Integer, default=0)
    pages_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, default=0)
    max_pages: Mapped[int] = mapped_column(Integer, default=200)
    llms_regenerated: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    change_summary_json: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(1024))

    site = relationship("Site", back_populates="crawl_jobs")
    generated_files = relationship("GeneratedFile", back_populates="crawl_job")
    crawl_tasks = relationship("CrawlTask", back_populates="crawl_job")
