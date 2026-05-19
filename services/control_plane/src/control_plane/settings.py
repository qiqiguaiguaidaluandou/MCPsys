from pydantic import Field
from pydantic_settings import SettingsConfigDict

from mcpsys_shared.settings import SharedSettings


class ControlPlaneSettings(SharedSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(default="dev-only-secret-change-me")
    jwt_expires_minutes: int = Field(default=60)

    # 健康检查 worker（spec §4.3 流程 C）。enabled=False 用于测试隔离。
    health_check_enabled: bool = Field(default=True)
    health_check_interval_seconds: int = Field(default=30, ge=5)
    health_check_timeout_seconds: float = Field(default=3.0, gt=0)
    health_check_concurrency: int = Field(default=8, ge=1)


settings = ControlPlaneSettings()
