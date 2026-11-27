"""API cho Raspberry Pi (xác thực bằng header X-API-Key)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_session
from ..models import Device
from ..schemas import CommandAck, CommandOut, ControlLogOut, IngestResult, PassageBatchIn, TelemetryIn
from ..security import get_current_device
from ..services import control_service, counter_service, ingest_service

router = APIRouter(prefix="/api/v1", tags=["device (Raspberry Pi)"])


def _check_batch(n: int) -> None:
    limit = get_settings().max_batch_size
    if n > limit:
        raise HTTPException(413, f"Tối đa {limit} lượt mỗi request, hãy chia nhỏ")


@router.post("/telemetry", response_model=IngestResult)
async def post_telemetry(
    body: TelemetryIn, device: Device = Depends(get_current_device), session: AsyncSession = Depends(get_session)
):
    """Nhịp định kỳ từ Pi: trạng thái phòng (PIR), khoảng cách, số đếm local; có thể kèm các lượt chưa gửi.
    Response chứa `count_today` (số chuẩn của server) và `pending_commands` (vd. lệnh reset)."""
    _check_batch(len(body.passages))
    return await ingest_service.process(session, device, body, body.passages)


@router.post("/passages", response_model=IngestResult)
async def post_passages(
    body: PassageBatchIn, device: Device = Depends(get_current_device), session: AsyncSession = Depends(get_session)
):
    """Gửi 1 hoặc nhiều lượt qua cửa (gửi ngay khi đếm được, hoặc gửi bù sau khi mất mạng)."""
    _check_batch(len(body.events))
    return await ingest_service.process(session, device, None, body.events)


@router.get("/device/commands", response_model=list[CommandOut])
async def poll_commands(device: Device = Depends(get_current_device), session: AsyncSession = Depends(get_session)):
    """Pi hỏi lệnh đang chờ (nếu không dùng MQTT và không gửi telemetry thường xuyên)."""
    cmds = await control_service.take_pending(session, device)
    await session.commit()
    return cmds


@router.post("/device/commands/{command_id}/ack", response_model=ControlLogOut)
async def ack_command(
    command_id: int,
    body: CommandAck,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
):
    """Pi xác nhận đã thực hiện lệnh (status = success | failed)."""
    return await control_service.ack_command(session, device, command_id, body)


@router.get("/device/state")
async def device_state(device: Device = Depends(get_current_device), session: AsyncSession = Depends(get_session)):
    """Pi lấy số đếm chuẩn khi khởi động lại (để LCD hiển thị đúng)."""
    today = await counter_service.count_for_day(session, device.id)
    return {
        "device_id": device.id,
        "device_uid": device.device_uid,
        "name": device.name,
        "date": today.date,
        "count_today": today.count,
        "last_reset_at": today.last_reset_at,
    }
