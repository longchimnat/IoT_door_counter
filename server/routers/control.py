"""Điều khiển thiết bị từ dashboard: nút "Đặt lại số đếm"."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import CommandType, ControlLog, User
from ..schemas import ControlLogOut, ControlRequest, ControlResult
from ..security import get_current_user
from ..services import control_service, counter_service
from ..services.realtime import hub
from .devices import get_device_or_404

router = APIRouter(prefix="/api/v1/devices", tags=["control"])


@router.post("/{device_id}/control", response_model=ControlResult, status_code=status.HTTP_202_ACCEPTED)
async def send_control(
    device_id: int,
    body: ControlRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Gửi lệnh xuống Pi. `reset_counter`: server về 0 ngay, Pi nhận lệnh qua MQTT hoặc response HTTP kế tiếp."""
    device = await get_device_or_404(session, device_id)
    cmd, delivered = await control_service.create_command(session, device, body.command, body.payload, user.username)
    today = await counter_service.count_for_day(session, device.id)
    if body.command == CommandType.reset_counter:
        await hub.broadcast(
            "counter_reset",
            device.id,
            {"count_today": today.count, "last_reset_at": today.last_reset_at, "by": user.username, "command_id": cmd.id},
        )
    return ControlResult(command=ControlLogOut.model_validate(cmd), delivered_via=delivered, count_today=today.count)


@router.post("/{device_id}/reset", response_model=ControlResult, status_code=status.HTTP_202_ACCEPTED)
async def reset_counter(device_id: int, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)):
    """Viết tắt của POST /control {"command": "reset_counter"}."""
    return await send_control(device_id, ControlRequest(command=CommandType.reset_counter), session, user)


@router.get("/{device_id}/control-logs", response_model=list[ControlLogOut])
async def control_logs(
    device_id: int,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    await get_device_or_404(session, device_id)
    return (
        await session.scalars(
            select(ControlLog).where(ControlLog.device_id == device_id).order_by(ControlLog.id.desc()).limit(limit)
        )
    ).all()
