from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()
