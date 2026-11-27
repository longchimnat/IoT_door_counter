"""Offline-tolerant HTTP client for the FastAPI backend."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from datetime import datetime, timezone

from . import config as cfg

log = logging.getLogger(__name__)


def iso_utc(ts: float | None = None) -> str:
    value = time.time() if ts is None else ts
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(timespec="milliseconds")


class ServerClient:
    """Queue passages durably and send telemetry/commands off the sensor loop."""

    def __init__(
        self,
        base_url: str = cfg.API_URL,
        api_key: str = cfg.API_KEY,
        device_id: str = cfg.DEVICE_ID,
        queue_path: str = cfg.QUEUE_FILE,
        timeout: float = cfg.HTTP_TIMEOUT_S,
        retry_interval: float = cfg.SEND_RETRY_INTERVAL_S,
        poll_interval: float = cfg.COMMAND_POLL_INTERVAL_S,
        heartbeat: float = cfg.STATE_HEARTBEAT_S,
        enabled: bool = True,
        max_queue: int = cfg.MAX_QUEUE,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.device_id = device_id
        self.queue_path = queue_path
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.poll_interval = poll_interval
        self.heartbeat = heartbeat
        self.max_queue = max_queue
        self.enabled = bool(enabled and self.base_url)

        self.online: bool | None = None
        self.sent_events = 0
        self.server_count: int | None = None
        self._queue: deque[dict] = deque()
        self._commands: deque[dict] = deque()
        self._command_ids: set[int] = set()
        self._acks: deque[dict] = deque()
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state: dict | None = None
        self._state_dirty = False
        self._state_sent_at = float("-inf")
        self._retry_after = 0.0
        self._next_poll = 0.0
        if self.enabled:
            self._load_queue()

    def fetch_state(self) -> dict | None:
        """Read the server's canonical count during startup; returns None offline."""
        if not self.enabled:
            return None
        try:
            state = self._request("GET", "/api/v1/device/state")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
            log.warning("Chưa lấy được trạng thái từ server: %s", exc)
            return None
        if isinstance(state, dict) and isinstance(state.get("count_today"), int):
            self.server_count = state["count_today"]
        return state if isinstance(state, dict) else None

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="server-client", daemon=True)
        self._thread.start()

    def send_event(self, total: int | None = None, delta: int = 1, ts: float | None = None, **metrics):
        """Add one passage to the durable queue. The server derives its own count."""
        if not self.enabled:
            return None
        event = {
            "event_id": str(uuid.uuid4()),
            "occurred_at": iso_utc(ts),
        }
        for key in ("min_distance_cm", "baseline_cm", "duration_ms"):
            if metrics.get(key) is not None:
                event[key] = metrics[key]
        with self._lock:
            self._queue.append(event)
            overflow = False
            while len(self._queue) > self.max_queue:
                self._queue.popleft()
                log.error("Hàng đợi đầy, bỏ lượt cũ nhất")
                overflow = True
            if overflow:
                self._rewrite_file()
            else:
                self._append_file(event)
        self._wake.set()
        return event

    def send_state(
        self,
        occupied: bool,
        ts: float | None = None,
        *,
        motion: bool | None = None,
        local_count: int | None = None,
        distance_cm: float | None = None,
    ) -> None:
        """Stage the latest room/sensor state for the next background request."""
        if not self.enabled:
            return
        state = {"recorded_at": iso_utc(ts), "room_occupied": bool(occupied)}
        if motion is not None:
            state["motion"] = bool(motion)
        if local_count is not None:
            state["local_count"] = max(0, int(local_count))
        if distance_cm is not None:
            state["distance_cm"] = max(0.0, float(distance_cm))
        with self._lock:
            self._state = state
            self._state_dirty = True
        self._wake.set()

    def consume_commands(self) -> list[dict]:
        with self._lock:
            result = list(self._commands)
            self._commands.clear()
            return result

    def consume_reset(self) -> bool:
        """Compatibility helper for callers that only handle a reset command."""
        commands = self.consume_commands()
        reset = [c for c in commands if c.get("command") == "reset_counter"]
        with self._lock:
            for cmd in commands:
                if cmd not in reset:
                    self._commands.append(cmd)
                    if "id" in cmd:
                        self._command_ids.add(int(cmd["id"]))
        return bool(reset)

    def ack_command(self, command_id: int, status: str = "success", detail: str | None = None) -> None:
        if not self.enabled:
            return
        ack = {"id": int(command_id), "status": status, "detail": detail}
        with self._lock:
            if not any(item["id"] == ack["id"] for item in self._acks):
                self._acks.append(ack)
        self._wake.set()

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def close(self, join_timeout: float = 3.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            self._thread = None

    def _run(self) -> None:
        wait = max(0.05, min(self.poll_interval, self.retry_interval))
        while not self._stop.is_set():
            self._wake.wait(timeout=wait)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self._cycle()
            except Exception:
                log.exception("Lỗi không mong đợi trong luồng mạng")
                self._retry_after = time.monotonic() + self.retry_interval

    def _cycle(self) -> None:
        now = time.monotonic()
        if now < self._retry_after:
            return
        ok = self._flush_events()
        if ok:
            ok = self._send_state_if_needed(now)
        if ok and now >= self._next_poll:
            ok = self._poll_commands()
            self._next_poll = now + self.poll_interval
        if ok:
            ok = self._flush_acks()
        self._set_online(ok)
        if not ok:
            self._retry_after = now + self.retry_interval

    def _flush_events(self) -> bool:
        sent = 0
        while True:
            with self._lock:
                batch = list(self._queue)[:200]
            if not batch:
                break
            try:
                result = self._request("POST", "/api/v1/passages", {"events": batch})
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 408, 429) or exc.code >= 500:
                    return False
                log.error("Server từ chối %d lượt chờ (HTTP %s); bỏ batch sai định dạng", len(batch), exc.code)
                self._remove_events(batch)
                continue
            except (urllib.error.URLError, OSError, ValueError):
                return False
            if not isinstance(result, dict):
                return False
            if isinstance(result.get("count_today"), int):
                self.server_count = result["count_today"]
            self._queue_commands(result.get("pending_commands", []))
            self._remove_events(batch)
            sent += len(batch)
        self.sent_events += sent
        return True

    def _remove_events(self, batch: list[dict]) -> None:
        ids = {event.get("event_id") for event in batch}
        with self._lock:
            self._queue = deque(event for event in self._queue if event.get("event_id") not in ids)
            self._rewrite_file()

    def _send_state_if_needed(self, now: float) -> bool:
        with self._lock:
            state = dict(self._state) if self._state else None
            due = self._state_dirty or now - self._state_sent_at >= self.heartbeat
        if state is None or not due:
            return True
        try:
            result = self._request("POST", "/api/v1/telemetry", state)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 408, 429) or exc.code >= 500:
                return False
            log.error("Server từ chối telemetry (HTTP %s)", exc.code)
            return True
        except (urllib.error.URLError, OSError, ValueError):
            return False
        if not isinstance(result, dict):
            return False
        if isinstance(result.get("count_today"), int):
            self.server_count = result["count_today"]
        self._queue_commands(result.get("pending_commands", []))
        with self._lock:
            if self._state == state:
                self._state_dirty = False
        self._state_sent_at = now
        return True

    def _poll_commands(self) -> bool:
        try:
            result = self._request("GET", "/api/v1/device/commands")
        except urllib.error.HTTPError as exc:
            return False if exc.code in (401, 403, 408, 429) or exc.code >= 500 else True
        except (urllib.error.URLError, OSError, ValueError):
            return False
        if isinstance(result, list):
            self._queue_commands(result)
        return True

    def _queue_commands(self, commands) -> None:
        if not isinstance(commands, list):
            return
        with self._lock:
            for command in commands:
                if not isinstance(command, dict) or "id" not in command:
                    continue
                command_id = int(command["id"])
                if command_id not in self._command_ids:
                    self._commands.append(command)
                    self._command_ids.add(command_id)
                    if command.get("command") == "reset_counter":
                        self.server_count = 0

    def _flush_acks(self) -> bool:
        while True:
            with self._lock:
                if not self._acks:
                    return True
                ack = self._acks[0]
            body = {"status": ack["status"], "detail": ack["detail"]}
            try:
                self._request("POST", f"/api/v1/device/commands/{ack['id']}/ack", body)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 408, 429) or exc.code >= 500:
                    return False
                log.error("Server từ chối ACK lệnh #%d (HTTP %s)", ack["id"], exc.code)
            except (urllib.error.URLError, OSError, ValueError):
                return False
            with self._lock:
                if self._acks and self._acks[0] is ack:
                    self._acks.popleft()
                self._command_ids.discard(int(ack["id"]))

    def _set_online(self, ok: bool) -> None:
        if ok and self.online is False:
            log.info("Đã kết nối lại server; còn %d lượt chờ", self.pending)
        elif not ok and self.online is not False:
            log.warning("Mất kết nối server; sẽ gửi bù (%d lượt chờ)", self.pending)
        self.online = ok

    def _request(self, method: str, path: str, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json", "X-API-Key": self.api_key}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            raw = response.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _load_queue(self) -> None:
        try:
            with open(self.queue_path, encoding="utf-8") as queue_file:
                for line in queue_file:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        log.warning("Bỏ dòng hỏng trong hàng đợi %s", self.queue_path)
                        continue
                    if isinstance(event, dict) and event.get("event_id") and event.get("occurred_at"):
                        self._queue.append(event)
        except FileNotFoundError:
            return
        if self._queue:
            log.info("Nạp %d lượt chờ từ %s", len(self._queue), self.queue_path)

    def _append_file(self, event: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self.queue_path) or ".", exist_ok=True)
            with open(self.queue_path, "a", encoding="utf-8") as queue_file:
                queue_file.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("Không lưu được lượt vào hàng đợi")

    def _rewrite_file(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.queue_path) or ".", exist_ok=True)
            temporary = self.queue_path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as queue_file:
                for event in self._queue:
                    queue_file.write(json.dumps(event, ensure_ascii=False) + "\n")
            os.replace(temporary, self.queue_path)
        except OSError:
            log.exception("Không cập nhật được file hàng đợi")
