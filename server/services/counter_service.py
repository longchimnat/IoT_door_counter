"""Nghiệp vụ đếm lượt: nhận lượt qua cửa, chống trùng, tính số lượt hôm nay, thống kê theo giờ/ngày.

Quy ước reset (chốt cho cả nhóm, xem docs/API.md):
- Bấm "Đặt lại" trên web -> server ghi 1 lệnh reset_counter vào control_logs, thời điểm reset = created_at.
- Số lượt hôm nay = số lượt có occurred_at >= max(0h hôm nay, lần reset gần nhất trong hôm nay).
- Dữ liệu lượt cũ KHÔNG bị xóa (giữ để làm bảng số liệu test); biểu đồ mặc định chỉ tính từ lần reset.
- Qua 0h ngày mới số đếm tự về 0 (không cần reset).
"""
from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import utcnow
from ..models import CommandType, ControlLog, Device, PassageEvent
from ..schemas import PassageIn


# ---------------- Thời gian ----------------
def local_today() -> date:
    return utcnow().astimezone(get_settings().tz).date()


def day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """[0h ngày d, 0h ngày d+1) theo giờ địa phương, đổi ra UTC."""
    tz = get_settings().tz
    start = datetime.combine(d, time.min, tzinfo=tz)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


# ---------------- Reset ----------------
async def last_reset_between(session: AsyncSession, device_id: int, start: datetime, end: datetime) -> datetime | None:
    return await session.scalar(
        select(func.max(ControlLog.created_at)).where(
            ControlLog.device_id == device_id,
            ControlLog.command == CommandType.reset_counter,
            ControlLog.created_at >= start,
            ControlLog.created_at < end,
        )
    )


async def _count(session: AsyncSession, device_id: int, start: datetime, end: datetime) -> int:
    return int(
        await session.scalar(
            select(func.count(PassageEvent.id)).where(
                PassageEvent.device_id == device_id,
                PassageEvent.occurred_at >= start,
                PassageEvent.occurred_at < end,
            )
        )
        or 0
    )


@dataclass
class TodayCount:
    date: date
    count: int                  # số lượt kể từ lần reset (hoặc 0h)
    total_day: int              # tổng lượt cả ngày (kể cả trước reset)
    last_reset_at: datetime | None
    last_passage_at: datetime | None


async def count_for_day(session: AsyncSession, device_id: int, d: date | None = None) -> TodayCount:
    d = d or local_today()
    start, end = day_bounds_utc(d)
    reset_at = await last_reset_between(session, device_id, start, end)
    effective_start = max(start, reset_at) if reset_at else start
    count = await _count(session, device_id, effective_start, end)
    total = await _count(session, device_id, start, end) if reset_at else count
    last_passage = await session.scalar(
        select(func.max(PassageEvent.occurred_at)).where(
            PassageEvent.device_id == device_id,
            PassageEvent.occurred_at >= start,
            PassageEvent.occurred_at < end,
        )
    )
    return TodayCount(d, count, total, reset_at, last_passage)


# ---------------- Nhận lượt ----------------
@dataclass
class IngestOutcome:
    accepted: list[PassageEvent] = field(default_factory=list)
    duplicates: int = 0
    debounced: int = 0
    rejected_future: int = 0


async def ingest_passages(session: AsyncSession, device: Device, events: Sequence[PassageIn]) -> IngestOutcome:
    """Lưu các lượt qua cửa. Không commit (router/caller commit).

    - Trùng event_id (Pi gửi bù sau khi mất Wi-Fi) -> bỏ qua, tính vào `duplicates`.
    - Hai lượt cách nhau < SERVER_DEBOUNCE_SECONDS -> chỉ giữ 1 (lớp bảo vệ thứ 2, Pi đã lọc 1s).
    - Timestamp ở tương lai quá MAX_CLOCK_SKEW_SECONDS -> lấy thời điểm server nhận.
    """
    s = get_settings()
    out = IngestOutcome()
    if not events:
        return out

    now = utcnow()
    max_future = now + timedelta(seconds=s.max_clock_skew_seconds)

    # 1) Loại trùng trong chính batch và với DB
    seen: set[str] = set()
    unique: list[PassageIn] = []
    for e in events:
        if e.event_id in seen:
            out.duplicates += 1
            continue
        seen.add(e.event_id)
        unique.append(e)

    existing = set(
        (
            await session.scalars(
                select(PassageEvent.event_uid).where(
                    PassageEvent.device_id == device.id, PassageEvent.event_uid.in_(list(seen))
                )
            )
        ).all()
    )
    fresh: list[PassageIn] = []
    for e in unique:
        if e.event_id in existing:
            out.duplicates += 1
        else:
            fresh.append(e)

    # 2) Chuẩn hóa thời gian
    normalized: list[tuple[datetime, PassageIn]] = []
    for e in fresh:
        ts = e.occurred_at
        if ts > max_future:
            out.rejected_future += 1
            ts = now
        normalized.append((ts, e))
    normalized.sort(key=lambda x: x[0])

    # 3) Chống đếm trùng theo thời gian (so với DB và với nhau)
    debounce = timedelta(seconds=s.server_debounce_seconds)
    kept_times: list[datetime] = []
    if debounce and normalized:
        lo = normalized[0][0] - debounce
        hi = normalized[-1][0] + debounce
        kept_times = sorted(
            (
                await session.scalars(
                    select(PassageEvent.occurred_at).where(
                        PassageEvent.device_id == device.id,
                        PassageEvent.occurred_at > lo,
                        PassageEvent.occurred_at < hi,
                    )
                )
            ).all()
        )

    for ts, e in normalized:
        if debounce:
            i = bisect.bisect_left(kept_times, ts)
            near = (i < len(kept_times) and kept_times[i] - ts < debounce) or (
                i > 0 and ts - kept_times[i - 1] < debounce
            )
            if near:
                out.debounced += 1
                continue
            kept_times.insert(i, ts)
        row = PassageEvent(
            device_id=device.id,
            event_uid=e.event_id,
            occurred_at=ts,
            min_distance_cm=e.min_distance_cm,
            baseline_cm=e.baseline_cm,
            duration_ms=e.duration_ms,
            received_at=now,
        )
        session.add(row)
        out.accepted.append(row)
    return out


# ---------------- Thống kê ----------------
async def hourly(session: AsyncSession, device_id: int, d: date, since_reset: bool = True) -> tuple[list[int], datetime | None]:
    """Trả về (24 số đếm theo giờ địa phương, last_reset_at)."""
    tz = get_settings().tz
    start, end = day_bounds_utc(d)
    reset_at = await last_reset_between(session, device_id, start, end)
    effective_start = max(start, reset_at) if (since_reset and reset_at) else start
    times = (
        await session.scalars(
            select(PassageEvent.occurred_at).where(
                PassageEvent.device_id == device_id,
                PassageEvent.occurred_at >= effective_start,
                PassageEvent.occurred_at < end,
            )
        )
    ).all()
    buckets = [0] * 24
    for t in times:
        buckets[t.astimezone(tz).hour] += 1
    return buckets, reset_at


async def daily(session: AsyncSession, device_id: int, days: int) -> list[tuple[date, int]]:
    """Tổng lượt mỗi ngày (cả ngày, không trừ reset) trong `days` ngày gần nhất."""
    tz = get_settings().tz
    today = local_today()
    first = today - timedelta(days=days - 1)
    start, _ = day_bounds_utc(first)
    _, end = day_bounds_utc(today)
    times = (
        await session.scalars(
            select(PassageEvent.occurred_at).where(
                PassageEvent.device_id == device_id,
                PassageEvent.occurred_at >= start,
                PassageEvent.occurred_at < end,
            )
        )
    ).all()
    counts: dict[date, int] = {first + timedelta(days=i): 0 for i in range(days)}
    for t in times:
        ld = t.astimezone(tz).date()
        if ld in counts:
            counts[ld] += 1
    return sorted(counts.items())
