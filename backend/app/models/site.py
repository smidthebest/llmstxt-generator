from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)

    pages = relationship("Page", back_populates="site", cascade="all, delete-orphan")
    crawl_jobs = relationship("CrawlJob", back_populates="site", cascade="all, delete-orphan")
    generated_files = relationship("GeneratedFile", back_populates="site", cascade="all, delete-orphan")
    schedule = relationship("MonitoringSchedule", back_populates="site", uselist=False, cascade="all, delete-orphan")
