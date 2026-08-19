from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    brightdata_api_key: str | None = None
    brightdata_zone: str | None = None
    brightdata_dataset_id: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
