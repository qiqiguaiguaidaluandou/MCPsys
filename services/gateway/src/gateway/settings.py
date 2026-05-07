from pydantic import Field
from pydantic_settings import SettingsConfigDict

from mcpsys_shared.settings import SharedSettings


class GatewaySettings(SharedSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    proxy_timeout_seconds: float = Field(default=30.0)
    proxy_verify_tls: bool = Field(default=True)
    api_key_cache_ttl_seconds: int = Field(default=60)
    service_cache_ttl_seconds: int = Field(default=60)
    telemetry_flush_interval_seconds: float = Field(default=1.0)
    telemetry_batch_size: int = Field(default=100)
    body_log_max_bytes: int = Field(default=64 * 1024)


settings = GatewaySettings()
