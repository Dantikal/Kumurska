from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+asyncpg://kumurska:kumurska@localhost:5433/kumurska"
    redis_url: str = "redis://localhost:6379/0"

    otp_length: int = 4
    otp_ttl_seconds: int = 300
    otp_resend_seconds: int = 60
    otp_max_attempts: int = 5
    otp_secret: str = INSECURE_SECRET

    jwt_secret: str = INSECURE_SECRET
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # "fake" — только для dev и test; реальные провайдеры подключаются отдельной задачей
    sms_provider: str = "fake"

    # Хранилище изображений (US-17): S3-совместимое, в dev — MinIO из docker-compose.yml
    s3_endpoint_url: str | None = "http://localhost:9010"
    s3_region: str = "us-east-1"
    s3_access_key: str = "kumurska"
    s3_secret_key: str = "kumurska-dev-secret"
    s3_bucket: str = "kumurska-content"
    # Публичный адрес бакета: из него собирается image_url
    s3_public_url: str = "http://localhost:9010/kumurska-content"


def ensure_prod_secrets(config: Settings) -> None:
    """В prod секреты обязаны прийти из окружения. Значения в ошибку не попадают."""
    if config.app_env != "prod":
        return
    insecure = [
        name
        for name in ("otp_secret", "jwt_secret")
        if getattr(config, name) == INSECURE_SECRET or len(getattr(config, name)) < 32
    ]
    if insecure:
        raise RuntimeError(
            f"В prod задайте через окружение (не короче 32 символов): {', '.join(insecure)}"
        )


settings = Settings()
ensure_prod_secrets(settings)
