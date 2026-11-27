"""WebSocket realtime cho dashboard: ws://<host>:8000/ws?token=<JWT>

Server đẩy các message dạng {"type", "device_id", "ts", "data"} với type:
  passage | room_state | device_status | counter_reset | command | command_ack | alert
Client có thể gửi "ping" để giữ kết nối, server trả "pong".
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from ..database import get_sessionmaker
from ..security import user_from_token
from ..services.realtime import hub

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    try:
        async with get_sessionmaker()() as session:
            await user_from_token(token, session)
    except HTTPException:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return
    await hub.connect(ws)
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(ws)
