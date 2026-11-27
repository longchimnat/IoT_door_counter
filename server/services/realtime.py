"""Quản lý kết nối WebSocket và đẩy sự kiện realtime lên dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

from ..database import utcnow

log = logging.getLogger(__name__)


class RealtimeHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("WS client connected (%d total)", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("WS client disconnected (%d total)", len(self._clients))

    async def broadcast(self, event_type: str, device_id: int | None, data: Any) -> None:
        """Gửi {type, device_id, ts, data} tới mọi dashboard đang mở."""
        if not self._clients:
            return
        message = json.dumps(
            jsonable_encoder({"type": event_type, "device_id": device_id, "ts": utcnow(), "data": data}),
            ensure_ascii=False,
        )
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=5)
            except Exception:  # client đã đóng hoặc mạng chậm
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


hub = RealtimeHub()
