"""Trạng thái thiết bị: heartbeat, online/offline, trạng thái phòng (PIR)."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_sessionmaker, utcnow
from ..models import Alert, AlertType, Device, DeviceStatus, SensorData
from ..schemas import AlertOut, DeviceOut, TelemetryIn
from .realtime import hub

log = logging.getLogger(__name__)


async def mark_online(session: AsyncSession, device: Device) -> bool:
    """Cập nhật last_ping; nếu trước đó offline thì chuyển online + tự đóng cảnh báo offline.
    Trả về True nếu trạng thái thay đổi. Không commit."""
    now = utcnow()
    device.last_ping = now
    if device.status == DeviceStatus.online:
        return False
    device.status = DeviceStatus.online
    await session.execute(
        update(Alert)
        .where(
            Alert.device_id == device.id,
            Alert.alert_type == AlertType.device_offline,
            Alert.is_resolved.is_(False),
        )
        .values(is_resolved=True, resolved_at=now)
    )
    return True


async def mark_offline(session: AsyncSession, device: Device, reason: str) -> Alert | None:
    """Chuyển offline và tạo cảnh báo (nếu chưa có cảnh báo offline đang mở). Không commit."""
    if device.status == DeviceStatus.offline:
        return None
    device.status = DeviceStatus.offline
    open_alert = await session.scalar(
        select(Alert).where(
            Alert.device_id == device.id,
            Alert.alert_type == AlertType.device_offline,
            Alert.is_resolved.is_(False),
        )
    )
    if open_alert:
        return None
    alert = Alert(device_id=device.id, alert_type=AlertType.device_offline, message=reason)
    session.add(alert)
    return alert


def apply_room_state(device: Device, data: TelemetryIn) -> bool:
    """Cập nhật trạng thái phòng hiện tại vào bảng devices. Trả về True nếu trạng thái phòng đổi."""
    changed = False
    if data.room_occupied is not None and data.room_occupied != device.room_occupied:
        device.room_occupied = data.room_occupied
        changed = True
    if data.last_motion_at is not None:
        device.last_motion_at = data.last_motion_at
    elif data.motion:
        device.last_motion_at = data.recorded_at or utcnow()
    if data.distance_cm is not None:
        device.last_distance_cm = data.distance_cm
    return changed


def build_sensor_row(device: Device, data: TelemetryIn) -> SensorData:
    return SensorData(
        device_id=device.id,
        room_occupied=data.room_occupied,
        motion=data.motion,
        last_motion_at=data.last_motion_at,
        distance_cm=data.distance_cm,
        local_count=data.local_count,
        extra=data.extra,
        recorded_at=data.recorded_at or utcnow(),
    )


async def broadcast_device(device: Device, event_type: str = "device_status") -> None:
    await hub.broadcast(event_type, device.id, DeviceOut.model_validate(device).model_dump(mode="json"))


# ---------------- Background: phát hiện thiết bị offline ----------------
async def check_offline_once() -> int:
    s = get_settings()
    threshold = utcnow() - timedelta(seconds=s.device_offline_seconds)
    changed: list[tuple[Device, Alert | None]] = []
    async with get_sessionmaker()() as session:
        devices = (
            await session.scalars(
                select(Device).where(
                    Device.status == DeviceStatus.online,
                    Device.last_ping.is_not(None),
                    Device.last_ping < threshold,
                )
            )
        ).all()
        for d in devices:
            alert = await mark_offline(
                session, d, f"Thiết bị '{d.name}' ({d.device_uid}) mất kết nối quá {s.device_offline_seconds} giây"
            )
            changed.append((d, alert))
        if changed:
            await session.commit()
            for d, alert in changed:
                await session.refresh(d)
                await broadcast_device(d)
                if alert is not None:
                    await session.refresh(alert)
                    await hub.broadcast("alert", d.id, AlertOut.model_validate(alert).model_dump(mode="json"))
                log.warning("Device %s -> offline", d.device_uid)
    return len(changed)


async def offline_monitor(stop: asyncio.Event) -> None:
    interval = get_settings().offline_check_interval_seconds
    while not stop.is_set():
        try:
            await check_offline_once()
        except Exception:
            log.exception("offline_monitor lỗi")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
