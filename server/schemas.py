"""Pydantic schemas: validate dữ liệu vào/ra của API."""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import AlertType, CommandStatus, CommandType, DeviceStatus


def _aware(v: datetime | None) -> datetime | None:
    """Timestamp không có múi giờ -> hiểu là giờ địa phương của server (Asia/Ho_Chi_Minh)."""
    if v is None:
        return None
    if v.tzinfo is None:
        from .config import get_settings

        v = v.replace(tzinfo=get_settings().tz)
    return v.astimezone(timezone.utc)


# ---------------- Auth ----------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str | None
    is_active: bool


# ---------------- Devices ----------------
class DeviceCreate(BaseModel):
    device_uid: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=255)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    location: str | None = Field(default=None, max_length=255)


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_uid: str
    name: str
    location: str | None
    status: DeviceStatus
    last_ping: datetime | None
    room_occupied: bool | None
    last_motion_at: datetime | None
    last_distance_cm: float | None
    created_at: datetime


class DeviceWithKey(DeviceOut):
    api_key: str


# ---------------- Device -> Server ----------------
class PassageIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=64, description="UUID do Pi sinh cho mỗi lượt (chống trùng khi gửi bù)")
    occurred_at: datetime = Field(description="ISO-8601; không có múi giờ thì hiểu là giờ Việt Nam")
    min_distance_cm: float | None = Field(default=None, ge=0, le=1000)
    baseline_cm: float | None = Field(default=None, ge=0, le=1000)
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)

    @field_validator("occurred_at")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return _aware(v)


class PassageBatchIn(BaseModel):
    events: list[PassageIn] = Field(min_length=1)


class TelemetryIn(BaseModel):
    recorded_at: datetime | None = Field(default=None, description="Mặc định = thời điểm server nhận")
    room_occupied: bool | None = None
    motion: bool | None = None
    last_motion_at: datetime | None = None
    distance_cm: float | None = Field(default=None, ge=0, le=1000)
    local_count: int | None = Field(default=None, ge=0)
    extra: dict | None = None
    passages: list[PassageIn] = Field(default_factory=list, description="Có thể gửi kèm các lượt chưa gửi")

    @field_validator("recorded_at", "last_motion_at")
    @classmethod
    def _to_utc(cls, v: datetime | None) -> datetime | None:
        return _aware(v)


class CommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    command: CommandType
    payload: dict | None
    status: CommandStatus
    created_at: datetime


class IngestResult(BaseModel):
    accepted: int
    duplicates: int
    debounced: int
    count_today: int
    last_reset_at: datetime | None
    pending_commands: list[CommandOut]


class CommandAck(BaseModel):
    status: CommandStatus = Field(description="success hoặc failed")
    detail: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _only_final(cls, v: CommandStatus) -> CommandStatus:
        if v not in (CommandStatus.success, CommandStatus.failed):
            raise ValueError("status phải là 'success' hoặc 'failed'")
        return v


# ---------------- Dashboard ----------------
class ControlRequest(BaseModel):
    command: CommandType = CommandType.reset_counter
    payload: dict | None = None


class ControlLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    command: CommandType
    payload: dict | None
    status: CommandStatus
    triggered_by: str
    detail: str | None
    created_at: datetime
    sent_at: datetime | None
    acked_at: datetime | None


class ControlResult(BaseModel):
    command: ControlLogOut
    delivered_via: list[str]
    count_today: int


class PassageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    event_uid: str
    occurred_at: datetime
    min_distance_cm: float | None
    baseline_cm: float | None
    duration_ms: int | None
    received_at: datetime


class SensorDataOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    room_occupied: bool | None
    motion: bool | None
    last_motion_at: datetime | None
    distance_cm: float | None
    local_count: int | None
    extra: dict | None
    recorded_at: datetime


class SummaryOut(BaseModel):
    device: DeviceOut
    date: date
    timezone: str
    count_today: int
    total_today_before_reset: int
    last_reset_at: datetime | None
    last_passage_at: datetime | None


class HourlyBucket(BaseModel):
    hour: int
    count: int


class HourlyOut(BaseModel):
    device_id: int
    date: date
    timezone: str
    since_reset: bool
    last_reset_at: datetime | None
    total: int
    buckets: list[HourlyBucket]


class DailyBucket(BaseModel):
    date: date
    count: int


class DailyOut(BaseModel):
    device_id: int
    timezone: str
    days: list[DailyBucket]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    alert_type: AlertType
    message: str
    is_resolved: bool
    created_at: datetime
    resolved_at: datetime | None


class Page(BaseModel):
    total: int
    limit: int
    offset: int
