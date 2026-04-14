from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://monitor:monitor@localhost:5432/monitoring"
    database_url_sync: str = "postgresql+psycopg2://monitor:monitor@localhost:5432/monitoring"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production-use-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    metrics_ingest_token: str = "dev-internal-metrics-token"
    demo_traffic_token: str = "dev-demo-traffic-token-change-me"

    # Alert thresholds (Celery tasks use these)
    alert_error_rate_percent: float = 15.0
    alert_error_window_seconds: int = 120
    alert_latency_ms: float = 2000.0
    alert_latency_window_seconds: int = 120
    alert_min_samples: int = 10
    alert_stale_seconds: int = 90

    default_admin_password: str = "admin-change-me"
    default_viewer_password: str = "viewer-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
