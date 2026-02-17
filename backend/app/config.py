from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/llmstxt"
    cors_origins: list[str] = ["http://localhost:5173"]
    max_crawl_depth: int = 3
    max_crawl_pages: int = 200
    crawl_concurrency: int = 5
    crawl_delay_ms: int = 200
    llmstxt_openai_key: str = ""
    llm_model: str = "gpt-5.2"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
