from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.constants import PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SITECHAT_",
        extra="ignore",
    )

    user_agent: str = "SitechatBot/1.0 (+https://github.com/OVECJOE/becoming-a-fde)"
    max_depth: int = 5
    crawl_delay_seconds: float = 3
    sitemap_max_depth: int = 3
    openai_timeout_seconds: float = 60.0
    openai_max_retries: int = 3
    db_path: Path = PROJECT_ROOT.joinpath("sitechat.db")
    chroma_path: Path = PROJECT_ROOT.joinpath(".chromadb-data")


settings = Settings()
