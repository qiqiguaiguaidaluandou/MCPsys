from pydantic import Field
from pydantic_settings import SettingsConfigDict

from mcpsys_shared.settings import SharedSettings


class ControlPlaneSettings(SharedSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(default="dev-only-secret-change-me")
    jwt_expires_minutes: int = Field(default=60)
    config_fernet_key: str | None = Field(default=None)


settings = ControlPlaneSettings()
