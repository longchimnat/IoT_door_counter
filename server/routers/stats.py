"""Dữ liệu cho dashboard: tổng quan, biểu đồ theo giờ/ngày, lịch sử, xuất CSV."""
from __future__ import annotations

import csv
import io
from datetime import date as date_t
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_session, utcnow
from ..models import PassageEvent, SensorData, User
from ..schemas import (
    DailyBucket,
    DailyOut,
    DeviceOut,
    HourlyBucket,
    HourlyOut,
    Page,
    PassageOut,
    SensorDataOut,
    SummaryOut,
    _aware,
)
from ..security import get_current_user
from ..services import counter_service
from .devices import get_device_or_404

router = APIRouter(prefix="/api/v1", tags=["stats"])


def _range(from_: datetime | None, to: datetime | None, default_hours: int = 24) -> tuple[datetime, datetime]:
    end = _aware(to) if to else utcnow()
    start = _aware(from_) if from_ else end - timedelta(hours=default_hours)
    if start >= end:
        raise HTTPException(422, "'from' phải nhỏ hơn 'to'")
    if end - start > timedelta(days=366):
        raise HTTPException(422, "Khoảng thời gian tối đa 366 ngày")
    return start, end


@router.get("/stats/summary", response_model=SummaryOut)
async def summary(device_id: int, session: AsyncSession = Depends(get_session), _: User = Depends(get_current_user)):
    """Số lượt hôm nay (sau reset), trạng thái phòng, trạng thái thiết bị."""
    device = await get_device_or_404(session, device_id)
    today = await counter_service.count_for_day(session, device_id)
    return SummaryOut(
        device=DeviceOut.model_validate(device),
        date=today.date,
        timezone=get_settings().timezone,
        count_today=today.count,
        total_today_before_reset=today.total_day,
        last_reset_at=today.last_reset_at,
        last_passage_at=today.last_passage_at,
    )


@router.get("/stats/hourly", response_model=HourlyOut)
async def stats_hourly(
    device_id: int,
    date: date_t | None = Query(None, description="YYYY-MM-DD, mặc định hôm nay"),
    since_reset: bool = Query(True, description="true: chỉ tính sau lần reset gần nhất trong ngày"),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Biểu đồ số lượt theo giờ (0h-23h, giờ Việt Nam)."""
    await get_device_or_404(session, device_id)
    d = date or counter_service.local_today()
    buckets, reset_at = await counter_service.hourly(session, device_id, d, since_reset)
    return HourlyOut(
        device_id=device_id,
        date=d,
        timezone=get_settings().timezone,
        since_reset=since_reset,
        last_reset_at=reset_at,
        total=sum(buckets),
        buckets=[HourlyBucket(hour=h, count=c) for h, c in enumerate(buckets)],
    )


@router.get("/stats/daily", response_model=DailyOut)
async def stats_daily(
    device_id: int,
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    await get_device_or_404(session, device_id)
    rows = await counter_service.daily(session, device_id, days)
    return DailyOut(device_id=device_id, timezone=get_settings().timezone, days=[DailyBucket(date=d, count=c) for d, c in rows])


class PassagePage(Page):
    items: list[PassageOut]


@router.get("/passages", response_model=PassagePage)
async def list_passages(
    device_id: int,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Danh sách lượt qua cửa (mới nhất trước). Mặc định 24 giờ gần nhất."""
    await get_device_or_404(session, device_id)
    start, end = _range(from_, to)
    cond = (PassageEvent.device_id == device_id, PassageEvent.occurred_at >= start, PassageEvent.occurred_at < end)
    total = await session.scalar(select(func.count(PassageEvent.id)).where(*cond)) or 0
    items = (
        await session.scalars(
            select(PassageEvent).where(*cond).order_by(PassageEvent.occurred_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return PassagePage(total=total, limit=limit, offset=offset, items=items)


@router.get("/passages/export.csv")
async def export_passages_csv(
    device_id: int,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Xuất CSV (mở được bằng Excel) để làm bảng số liệu test. Mặc định 24 giờ gần nhất."""
    device = await get_device_or_404(session, device_id)
    start, end = _range(from_, to)
    rows = (
        await session.scalars(
            select(PassageEvent)
            .where(PassageEvent.device_id == device_id, PassageEvent.occurred_at >= start, PassageEvent.occurred_at < end)
            .order_by(PassageEvent.occurred_at)
        )
    ).all()
    tz = get_settings().tz
    buf = io.StringIO()
    buf.write("﻿")  # BOM để Excel hiển thị đúng tiếng Việt
    w = csv.writer(buf)
    w.writerow(["stt", "thoi_gian", "ngay", "gio", "event_id", "min_distance_cm", "baseline_cm", "duration_ms", "received_at"])
    for i, r in enumerate(rows, 1):
        lt = r.occurred_at.astimezone(tz)
        w.writerow([
            i, lt.strftime("%Y-%m-%d %H:%M:%S"), lt.date().isoformat(), lt.hour, r.event_uid,
            r.min_distance_cm, r.baseline_cm, r.duration_ms, r.received_at.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S"),
        ])
    filename = f"passages_{device.device_uid}_{start.astimezone(tz):%Y%m%d}_{end.astimezone(tz):%Y%m%d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/telemetry/history", response_model=list[SensorDataOut])
async def telemetry_history(
    device_id: int,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Lịch sử telemetry (trạng thái phòng, khoảng cách, số đếm local) - cũ trước, mới sau."""
    await get_device_or_404(session, device_id)
    start, end = _range(from_, to)
    rows = (
        await session.scalars(
            select(SensorData)
            .where(SensorData.device_id == device_id, SensorData.recorded_at >= start, SensorData.recorded_at < end)
            .order_by(SensorData.recorded_at.desc())
            .limit(limit)
        )
    ).all()
    return list(reversed(rows))
