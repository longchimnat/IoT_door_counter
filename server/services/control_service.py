"""Lệnh điều khiển xuống thiết bị (hiện có: reset_counter) - lưu control_logs, gửi qua MQTT/HTTP, nhận ack."""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import utcnow
from ..models import Alert, AlertType, CommandStatus, CommandType, ControlLog, Device
from ..schemas import AlertOut, CommandAck, CommandOut, ControlLogOut
from .realtime import hub

log = logging.getLogger(__name__)

ACTIVE = (CommandStatus.pending, CommandStatus.sent)


def command_message(cmd: ControlLog) -> dict:
    """Payload gửi xuống thiết bị (MQTT topic .../control hoặc trong response HTTP)."""
    return CommandOut.model_validate(cmd).model_dump(mode="json")


async def create_command(
    session: AsyncSession, device: Device, command: CommandType, payload: dict | None, triggered_by: str
) -> tuple[ControlLog, list[str]]:
    """Tạo lệnh, thay thế lệnh cùng loại còn treo, thử gửi MQTT. Commit bên trong.
    Trả về (lệnh, danh sách kênh đã gửi)."""
    from ..mqtt.bridge import bridge  # tránh import vòng

    await session.execute(
        update(ControlLog)
        .where(ControlLog.device_id == device.id, ControlLog.command == command, ControlLog.status.in_(ACTIVE))
        .values(status=CommandStatus.superseded, detail="Bị thay bằng lệnh mới hơn")
    )
    cmd = ControlLog(device_id=device.id, command=command, payload=payload or {}, triggered_by=triggered_by)
    session.add(cmd)
    await session.commit()
    await session.refresh(cmd)

    delivered = ["http_poll"]  # thiết bị luôn nhận được qua response HTTP / GET commands
    if await bridge.publish_command(device.device_uid, command_message(cmd)):
        cmd.status = CommandStatus.sent
        cmd.sent_at = utcnow()
        await session.commit()
        await session.refresh(cmd)
        delivered.insert(0, "mqtt")
    log.info("Command %s #%d -> %s via %s", command.value, cmd.id, device.device_uid, delivered)
    await hub.broadcast("command", device.id, ControlLogOut.model_validate(cmd).model_dump(mode="json"))
    return cmd, delivered


async def take_pending(session: AsyncSession, device: Device) -> list[ControlLog]:
    """Lấy các lệnh chưa ack để trả về cho thiết bị qua HTTP; đánh dấu sent. Không commit."""
    cmds = (
        await session.scalars(
            select(ControlLog)
            .where(ControlLog.device_id == device.id, ControlLog.status.in_(ACTIVE))
            .order_by(ControlLog.id)
        )
    ).all()
    now = utcnow()
    for c in cmds:
        if c.status == CommandStatus.pending:
            c.status = CommandStatus.sent
            c.sent_at = now
    return list(cmds)


async def ack_command(session: AsyncSession, device: Device, command_id: int, ack: CommandAck) -> ControlLog:
    cmd = await session.get(ControlLog, command_id)
    if cmd is None or cmd.device_id != device.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy lệnh")
    if cmd.status in (CommandStatus.success, CommandStatus.failed):
        return cmd  # ack lặp lại -> idempotent
    cmd.status = ack.status
    cmd.detail = ack.detail
    cmd.acked_at = utcnow()
    alert = None
    if ack.status == CommandStatus.failed:
        alert = Alert(
            device_id=device.id,
            alert_type=AlertType.command_failed,
            message=f"Lệnh {cmd.command.value} #{cmd.id} thất bại: {ack.detail or 'không rõ lý do'}",
        )
        session.add(alert)
    await session.commit()
    await session.refresh(cmd)
    await hub.broadcast("command_ack", device.id, ControlLogOut.model_validate(cmd).model_dump(mode="json"))
    if alert is not None:
        await session.refresh(alert)
        await hub.broadcast("alert", device.id, AlertOut.model_validate(alert).model_dump(mode="json"))
    return cmd
