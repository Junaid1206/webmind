from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    brightdata_api_key: str | None = None
    brightdata_zone: str | None = None
    brightdata_collector_id: str | None = None
    brightdata_dataset_id: str | None = None
    llm_api_key: str | None = None
    # Is line ko update karo:
    llm_model: str | None = "gemini-2.5-flash"
    llm_base_url: str | None = None
    database_url: str | None = f"sqlite:///{(PROJECT_ROOT / 'webmind.db').as_posix()}"
    webmind_api_key: str | None = None
    rate_limit_per_minute: int = 30
    brightdata_request_timeout_seconds: float = 30.0
    brightdata_poll_interval_seconds: float = 5.0
    brightdata_max_poll_attempts: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
