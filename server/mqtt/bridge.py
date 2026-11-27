"""MQTT bridge: backend subscribe dữ liệu từ Pi và publish lệnh xuống Pi.

Topic (prefix mặc định `iot/devices`, {uid} = devices.device_uid):
  Uplink   iot/devices/{uid}/telemetry    JSON TelemetryIn + "api_key" (có thể kèm "passages": [...])
  Uplink   iot/devices/{uid}/control/ack  {"api_key", "command_id", "status": "success|failed", "detail"}
  Status   iot/devices/{uid}/status       "online" | "offline" (hoặc {"status": ...}); Pi đặt LWT = "offline", retain
  Downlink iot/devices/{uid}/control      {"id", "command": "reset_counter", "payload", "status", "created_at"}  (QoS 1)
  Downlink iot/devices/{uid}/sync         {"count_today", "last_reset_at"} sau mỗi gói telemetry
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging

from pydantic import ValidationError
from sqlalchemy import select

from ..config import get_settings
from ..database import get_sessionmaker
from ..models import Device
from ..schemas import CommandAck, TelemetryIn

log = logging.getLogger(__name__)

try:
    import aiomqtt
except ImportError:  # pragma: no cover
    aiomqtt = None  # type: ignore[assignment]


class MqttBridge:
    def __init__(self) -> None:
        self._client = None
        self._task: asyncio.Task | None = None
        self.connected = False

    # ---------- vòng đời ----------
    def start(self) -> None:
        s = get_settings()
        if not s.mqtt_enabled:
            log.info("MQTT tắt (MQTT_ENABLED=false) - thiết bị dùng HTTP")
            return
        if aiomqtt is None:
            log.error("Chưa cài aiomqtt - không bật được MQTT")
            return
        self._task = asyncio.create_task(self._run(), name="mqtt-bridge")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        self.connected = False

    async def _run(self) -> None:
        s = get_settings()
        p = s.mqtt_topic_prefix.rstrip("/")
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=s.mqtt_host,
                    port=s.mqtt_port,
                    username=s.mqtt_username,
                    password=s.mqtt_password,
                    identifier=s.mqtt_client_id,
                    keepalive=30,
                ) as client:
                    self._client = client
                    self.connected = True
                    log.info("MQTT connected %s:%s", s.mqtt_host, s.mqtt_port)
                    for t in (f"{p}/+/telemetry", f"{p}/+/control/ack", f"{p}/+/status"):
                        await client.subscribe(t, qos=1)
                    async for message in client.messages:
                        try:
                            await self._handle(str(message.topic), message.payload)
                        except Exception:
                            log.exception("Lỗi xử lý MQTT message trên %s", message.topic)
            except asyncio.CancelledError:
                raise
            except NotImplementedError:
                # Windows + ProactorEventLoop không hỗ trợ add_reader mà paho/aiomqtt cần
                log.error(
                    "MQTT không chạy được trên event loop hiện tại (Windows). "
                    "Chạy bằng 'python -m server' hoặc Docker, hoặc để MQTT_ENABLED=false và dùng HTTP."
                )
                return
            except Exception as exc:  # aiomqtt.MqttError, OSError...
                log.warning("MQTT mất kết nối (%s) - thử lại sau %ss", exc, s.mqtt_reconnect_seconds)
            finally:
                self.connected = False
                self._client = None
            await asyncio.sleep(s.mqtt_reconnect_seconds)

    # ---------- publish ----------
    async def publish(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> bool:
        client = self._client
        if client is None or not self.connected:
            return False
        try:
            await client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)
            return True
        except Exception as exc:
            log.warning("MQTT publish %s lỗi: %s", topic, exc)
            return False

    async def publish_command(self, device_uid: str, message: dict) -> bool:
        p = get_settings().mqtt_topic_prefix.rstrip("/")
        return await self.publish(f"{p}/{device_uid}/control", message, qos=1)

    # ---------- subscribe handlers ----------
    async def _handle(self, topic: str, raw: bytes | bytearray | str | None) -> None:
        from ..services import control_service, device_service, ingest_service

        s = get_settings()
        prefix = s.mqtt_topic_prefix.rstrip("/") + "/"
        if not topic.startswith(prefix):
            return
        parts = topic[len(prefix):].split("/")
        if len(parts) < 2:
            return
        device_uid, kind = parts[0], "/".join(parts[1:])

        text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else (raw or "")
        try:
            body = json.loads(text) if text.strip().startswith(("{", "[")) else text.strip()
        except json.JSONDecodeError:
            log.warning("MQTT %s: payload không phải JSON hợp lệ", topic)
            return

        async with get_sessionmaker()() as session:
            device = await session.scalar(select(Device).where(Device.device_uid == device_uid))
            if device is None:
                log.warning("MQTT: device_uid '%s' chưa đăng ký - bỏ qua", device_uid)
                return

            if kind == "status":
                value = body.get("status") if isinstance(body, dict) else body
                if value == "online":
                    if await device_service.mark_online(session, device):
                        await session.commit()
                        await session.refresh(device)
                        await device_service.broadcast_device(device)
                    else:
                        await session.commit()
                elif value == "offline":
                    alert = await device_service.mark_offline(session, device, f"Thiết bị '{device.name}' báo offline (MQTT LWT)")
                    await session.commit()
                    await session.refresh(device)
                    await device_service.broadcast_device(device)
                    if alert is not None:
                        from ..schemas import AlertOut
                        from ..services.realtime import hub

                        await session.refresh(alert)
                        await hub.broadcast("alert", device.id, AlertOut.model_validate(alert).model_dump(mode="json"))
                return

            if not isinstance(body, dict):
                log.warning("MQTT %s: cần JSON object", topic)
                return
            api_key = str(body.pop("api_key", ""))
            if not hmac.compare_digest(api_key, device.api_key):
                log.warning("MQTT %s: api_key sai - bỏ qua", topic)
                return

            if kind == "telemetry":
                try:
                    data = TelemetryIn.model_validate(body)
                except ValidationError as e:
                    log.warning("MQTT %s: dữ liệu sai định dạng: %s", topic, e.errors())
                    return
                if len(data.passages) > s.max_batch_size:
                    log.warning("MQTT %s: quá %d lượt trong 1 gói", topic, s.max_batch_size)
                    return
                result = await ingest_service.process(session, device, data, data.passages)
                await self.publish(
                    f"{prefix}{device_uid}/sync",
                    {"count_today": result.count_today, "last_reset_at": result.last_reset_at.isoformat() if result.last_reset_at else None},
                    qos=0,
                )
                for cmd in result.pending_commands:  # gửi lại lệnh chưa ack
                    await self.publish_command(device_uid, cmd.model_dump(mode="json"))
            elif kind == "control/ack":
                try:
                    cid = int(body.pop("command_id"))
                    ack = CommandAck.model_validate(body)
                except (KeyError, ValueError, TypeError, ValidationError) as e:
                    log.warning("MQTT %s: ack sai định dạng: %s", topic, e)
                    return
                try:
                    await control_service.ack_command(session, device, cid, ack)
                except Exception as e:  # HTTPException 404
                    log.warning("MQTT %s: ack lỗi: %s", topic, getattr(e, "detail", e))


bridge = MqttBridge()
