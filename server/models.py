"""ORM models - schema CSDL cho đề tài 2: Đếm lượt người qua cửa.

Bảng:
- users          : tài khoản đăng nhập dashboard (JWT)
- devices        : Raspberry Pi gắn ở cửa (api_key, trạng thái online, trạng thái phòng hiện tại)
- passage_events : mỗi dòng = 1 lượt người qua cửa (HC-SR04 bị chắn rồi trở lại)
- sensor_data    : nhịp telemetry định kỳ (trạng thái phòng từ PIR, khoảng cách, số đếm local)
- control_logs   : lệnh gửi xuống thiết bị (reset_counter) và trạng thái thực thi
- alerts         : cảnh báo (thiết bị offline, lệnh thất bại)
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime, utcnow


class DeviceStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    unknown = "unknown"


class CommandType(str, enum.Enum):
    reset_counter = "reset_counter"


class CommandStatus(str, enum.Enum):
    pending = "pending"        # đã tạo, chưa gửi được qua MQTT (thiết bị sẽ nhận qua HTTP)
    sent = "sent"              # đã publish MQTT, chờ ack
    success = "success"        # thiết bị xác nhận đã thực hiện
    failed = "failed"          # thiết bị báo lỗi
    superseded = "superseded"  # bị thay bằng lệnh mới cùng loại trước khi thiết bị nhận


class AlertType(str, enum.Enum):
    device_offline = "device_offline"
    command_failed = "command_failed"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    # native_enum=False -> lưu dạng VARCHAR + CHECK, chạy giống nhau trên SQLite/PostgreSQL
    return Enum(e, name=name, native_enum=False, validate_strings=True, length=20)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # dùng trong MQTT topic
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    api_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(_enum(DeviceStatus, "device_status"), default=DeviceStatus.unknown, nullable=False)
    last_ping: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Trạng thái phòng hiện tại (theo PIR, báo lên từ Pi)
    room_occupied: Mapped[bool | None] = mapped_column(Boolean)
    last_motion_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_distance_cm: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    passages: Mapped[list[PassageEvent]] = relationship(back_populates="device", cascade="all, delete-orphan", passive_deletes=True)


class PassageEvent(Base):
    __tablename__ = "passage_events"
    __table_args__ = (
        UniqueConstraint("device_id", "event_uid", name="uq_passage_device_event"),
        Index("ix_passage_device_time", "device_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    event_uid: Mapped[str] = mapped_column(String(64), nullable=False)  # UUID do Pi sinh -> gửi bù không bị trùng
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)  # thời điểm người đi qua (theo Pi)
    min_distance_cm: Mapped[float | None] = mapped_column(Float)  # khoảng cách nhỏ nhất khi bị chắn
    baseline_cm: Mapped[float | None] = mapped_column(Float)      # khoảng cách nền (cửa trống)
    duration_ms: Mapped[int | None] = mapped_column(Integer)      # thời gian bị chắn
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    device: Mapped[Device] = relationship(back_populates="passages")


class SensorData(Base):
    __tablename__ = "sensor_data"
    __table_args__ = (Index("ix_sensor_device_time", "device_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    room_occupied: Mapped[bool | None] = mapped_column(Boolean)
    motion: Mapped[bool | None] = mapped_column(Boolean)  # PIR có chuyển động tại thời điểm gửi
    last_motion_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    distance_cm: Mapped[float | None] = mapped_column(Float)
    local_count: Mapped[int | None] = mapped_column(Integer)  # số lượt Pi đang hiển thị trên LCD
    extra: Mapped[dict | None] = mapped_column(JSON)  # dữ liệu tùy ý khác (nhiệt độ CPU, rssi...)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


class ControlLog(Base):
    __tablename__ = "control_logs"
    __table_args__ = (Index("ix_control_device_time", "device_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    command: Mapped[CommandType] = mapped_column(_enum(CommandType, "command_type"), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[CommandStatus] = mapped_column(_enum(CommandStatus, "command_status"), default=CommandStatus.pending, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_device_resolved", "device_id", "is_resolved"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    alert_type: Mapped[AlertType] = mapped_column(_enum(AlertType, "alert_type"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
