from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CrawlTask(Base, TimestampMixin):
    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    crawl_job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(Text)

    site = relationship("Site", back_populates="crawl_tasks")
    crawl_job = relationship("CrawlJob", back_populates="crawl_tasks")
