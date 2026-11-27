"""Cấu hình server, đọc từ biến môi trường hoặc file .env."""
from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "IoT De tai 2 - Dem luot nguoi qua cua"
    environment: str = "development"  # development | production
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"  # danh sách cách nhau bởi dấu phẩy
    timezone: str = "Asia/Ho_Chi_Minh"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/iot_detai2.db"
    auto_create_tables: bool = True  # dev: tự tạo bảng; prod/docker: dùng alembic
    db_echo: bool = False

    # --- Auth ---
    jwt_secret: str = "change-me-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # --- Thiết bị mặc định (seed lúc khởi động để nhóm Pi dùng ngay) ---
    default_device_uid: str = "door-01"
    default_device_name: str = "Cửa thư viện"
    default_device_location: str = "Thư viện tầng 1"
    default_device_api_key: str = "dev-door-01-key-change-me"

    # --- Nghiệp vụ ---
    device_offline_seconds: int = Field(default=90, ge=10)
    offline_check_interval_seconds: int = Field(default=15, ge=1)
    server_debounce_seconds: float = Field(default=1.0, ge=0)  # 0 = tắt chống trùng phía server
    max_batch_size: int = Field(default=500, ge=1)
    max_clock_skew_seconds: int = Field(default=300, ge=0)  # chặn timestamp ở tương lai quá xa

    # --- MQTT ---
    mqtt_enabled: bool = False
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_client_id: str = "iot-detai2-backend"
    mqtt_topic_prefix: str = "iot/devices"
    mqtt_reconnect_seconds: int = 5

    @field_validator("mqtt_username", "mqtt_password", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        return v or None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
