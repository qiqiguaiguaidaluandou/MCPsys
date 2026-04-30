from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SharedSettings(BaseSettings):
    """Shared settings consumed by both control_plane and gateway."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = Field(default="mcpsys")
    postgres_password: str = Field(default="changeme")
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="mcpsys")

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)

    log_level: str = Field(default="INFO")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"
