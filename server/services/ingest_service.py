"""Luồng xử lý dữ liệu thiết bị gửi lên (dùng chung cho HTTP và MQTT)."""
from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Device
from ..schemas import CommandOut, DeviceOut, IngestResult, PassageIn, PassageOut, TelemetryIn
from . import counter_service, device_service
from .control_service import take_pending
from .realtime import hub

log = logging.getLogger(__name__)


async def _process_once(session: AsyncSession, device: Device, telemetry: TelemetryIn | None, passages: Sequence[PassageIn]):
    status_changed = await device_service.mark_online(session, device)
    outcome = await counter_service.ingest_passages(session, device, passages)
    room_changed = False
    if telemetry is not None:
        room_changed = device_service.apply_room_state(device, telemetry)
        session.add(device_service.build_sensor_row(device, telemetry))
    pending = await take_pending(session, device)
    await session.commit()
    return status_changed, room_changed, outcome, pending


async def process(
    session: AsyncSession,
    device: Device,
    telemetry: TelemetryIn | None = None,
    passages: Sequence[PassageIn] = (),
) -> IngestResult:
    device_id = device.id
    try:
        status_changed, room_changed, outcome, pending = await _process_once(session, device, telemetry, passages)
    except IntegrityError:
        # Hai request gửi cùng event_id cùng lúc -> thử lại, lần này sẽ thấy bản ghi đã có và coi là trùng
        await session.rollback()
        device = await session.get(Device, device_id)
        status_changed, room_changed, outcome, pending = await _process_once(session, device, telemetry, passages)

    today = await counter_service.count_for_day(session, device.id)

    # ---- realtime lên dashboard ----
    await session.refresh(device)
    if status_changed:
        await device_service.broadcast_device(device)
    for row in outcome.accepted:
        await hub.broadcast(
            "passage",
            device.id,
            {**PassageOut.model_validate(row).model_dump(mode="json"), "count_today": today.count},
        )
    if telemetry is not None:
        await hub.broadcast(
            "room_state",
            device.id,
            {
                **DeviceOut.model_validate(device).model_dump(mode="json"),
                "room_changed": room_changed,
                "count_today": today.count,
                "local_count": telemetry.local_count,
            },
        )
    if outcome.accepted or outcome.duplicates or outcome.debounced:
        log.info(
            "%s: +%d lượt (trùng %d, chống dội %d) -> hôm nay %d",
            device.device_uid, len(outcome.accepted), outcome.duplicates, outcome.debounced, today.count,
        )

    return IngestResult(
        accepted=len(outcome.accepted),
        duplicates=outcome.duplicates,
        debounced=outcome.debounced,
        count_today=today.count,
        last_reset_at=today.last_reset_at,
        pending_commands=[CommandOut.model_validate(c) for c in pending],
    )
