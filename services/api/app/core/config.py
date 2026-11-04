from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+asyncpg://kumurska:kumurska@localhost:5433/kumurska"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
