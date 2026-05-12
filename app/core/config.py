from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "enterprise-hr-ticket-backend"
    environment: str = "local"
    debug: bool = True

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/enterprise_hr_ticket"
    test_database_url: str = "sqlite+pysqlite:///:memory:"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    internal_api_key: str = "change-me-internal-api-key"

    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
