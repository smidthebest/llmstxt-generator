from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class GeneratedFile(Base, TimestampMixin):
    __tablename__ = "generated_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    crawl_job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    site = relationship("Site", back_populates="generated_files")
    crawl_job = relationship("CrawlJob", back_populates="generated_files")
