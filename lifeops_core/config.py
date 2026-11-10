from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Env var names are explicit via validation aliases so that infra vars keep
    their conventional names (DATABASE_URL, MINIO_ENDPOINT, ...) while
    LifeOps-specific flags are prefixed LIFEOPS_.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------ identity ------------------------------
    app_name: str = "lifeops"
    environment: str = Field("local", validation_alias="LIFEOPS_ENV")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    # Reporting/day-boundary timezone. UTC+7 for this deployment.
    timezone_name: str = Field("Asia/Ho_Chi_Minh", validation_alias="LIFEOPS_TIMEZONE")

    # Optional stable UUID for the seeded primary user.
    default_user_id: str | None = Field(None, validation_alias="LIFEOPS_DEFAULT_USER_ID")
    default_user_email: str = "owner@lifeops.local"
    default_user_display_name: str = "Life Owner"

    # ------------------------------ database ------------------------------
    database_url: str = Field(
        "postgresql+psycopg://lifeops:lifeops@localhost:5432/lifeops",
        validation_alias="DATABASE_URL",
    )

    # ------------------------------ MinIO / S3 ----------------------------
    minio_endpoint: str = Field("localhost:9000", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field("lifeops", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field("lifeops-secret", validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field("lifeops", validation_alias="MINIO_BUCKET")
    minio_secure: bool = Field(False, validation_alias="MINIO_SECURE")

    def __repr__(self) -> str:  # keep secrets out of logs
        return (
            f"Settings(app_name={self.app_name}, environment={self.environment}, "
            f"timezone={self.timezone_name})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
