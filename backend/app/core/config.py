from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    brightdata_api_key: str | None = None
    brightdata_zone: str | None = None
    brightdata_dataset_id: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = "gpt-4o-mini"
    llm_base_url: str | None = None
    database_url: str | None = "sqlite:///./webmind.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
