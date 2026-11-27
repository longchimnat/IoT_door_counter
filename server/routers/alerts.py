from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session, utcnow
from ..models import Alert, User
from ..schemas import AlertOut
from ..security import get_current_user
from ..services.realtime import hub

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    device_id: int | None = None,
    resolved: bool | None = Query(None, description="lọc theo trạng thái đã xử lý"),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(Alert)
    if device_id is not None:
        q = q.where(Alert.device_id == device_id)
    if resolved is not None:
        q = q.where(Alert.is_resolved.is_(resolved))
    return (await session.scalars(q.order_by(Alert.id.desc()).limit(limit))).all()


@router.post("/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(alert_id: int, session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy cảnh báo")
    if not alert.is_resolved:
        alert.is_resolved = True
        alert.resolved_at = utcnow()
        await session.commit()
        await session.refresh(alert)
        await hub.broadcast("alert", alert.device_id, AlertOut.model_validate(alert).model_dump(mode="json"))
    return alert
