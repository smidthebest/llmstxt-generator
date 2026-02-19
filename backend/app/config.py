from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/llmstxt"
    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def normalize_database_url(self):
        # Railway provides postgresql://, SQLAlchemy+asyncpg needs postgresql+asyncpg://
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        return self
    max_crawl_depth: int = 3
    max_crawl_pages: int = 200
    crawl_concurrency: int = 20
    crawl_delay_ms: int = 50
    crawl_request_timeout_seconds: float = 15.0
    crawl_timeout_streak_threshold: int = 8
    crawl_timeout_rate_threshold: float = 0.7
    crawl_timeout_min_samples: int = 12
    crawl_progress_stall_seconds: int = 30
    crawl_circuit_cooldown_seconds: int = 120
    # Safety valve. Disabled by default to avoid cutting off large healthy crawls.
    crawl_max_duration_seconds: int = 0
    # Low-yield Playwright probe: if a shallow page has very few crawlable
    # links after static extraction, render it with Playwright and compare.
    crawl_js_probe_low_links: int = 1
    crawl_js_probe_max_depth: int = 1
    crawl_js_probe_max_attempts: int = 3
    crawl_js_probe_promote_links: int = 3
    llmstxt_openai_key: str = ""
    llm_model: str = "gpt-5.2"

    run_scheduler: bool = False
    worker_id: str = ""
    worker_max_concurrent_tasks: int = 3
    task_lease_seconds: int = 60
    task_poll_interval_ms: int = 1000
    task_max_attempts: int = 5
    task_heartbeat_interval_seconds: int = 10
    scheduler_sync_interval_seconds: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
