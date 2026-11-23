"""client.py - Gửi dữ liệu từ Pi lên web server, không chặn vòng đếm.

Người phụ trách: A (Long).

Việc gửi chạy ở luồng nền; vòng đếm chỉ đưa sự kiện vào hàng đợi (tức thì).
Mất mạng thì sự kiện nằm trong hàng đợi và được lưu ra file QUEUE_FILE, nên kể cả
khi Pi khởi động lại vẫn gửi bù, không mất lượt. Mỗi sự kiện có event_id duy nhất
để server bỏ qua bản trùng nếu lần gửi trước đã tới nhưng phản hồi bị mất.

GIAO DIỆN VỚI SERVER (GIẢ ĐỊNH - đối chiếu với docs/API.md và server/app.py):
  POST {API_URL}/api/events   mỗi lượt đi qua
      {"event_id": "<uuid hex>", "device_id": "pi-door-1",
       "timestamp": "2026-11-23T10:15:30.123Z", "type": "pass", "delta": 1, "total": 12}
  POST {API_URL}/api/state    trạng thái phòng, gửi khi đổi và định kỳ
      {"device_id": "pi-door-1", "timestamp": "...", "occupied": true, "state": "occupied"}
  GET  {API_URL}/api/status?device_id=pi-door-1   web có bấm reset chưa
      -> {"reset_seq": 3}   (số tăng mỗi lần bấm reset; lần đọc đầu chỉ ghi nhớ)
Mã 2xx = thành công; 4xx (trừ 408, 429) = server từ chối, bỏ sự kiện đó để không kẹt
hàng đợi; còn lại (5xx, mất mạng, hết giờ) = giữ lại và thử lại sau.
Thời gian dùng ISO 8601 UTC (hậu tố Z); web tự đổi sang múi giờ Việt Nam khi hiển thị.
Sửa đường dẫn trong config.py, sửa cấu trúc JSON trong send_event/send_state ở đây.
"""
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

from pi import config as cfg

log = logging.getLogger(__name__)


def iso_utc(ts=None):
    """Thời gian ISO 8601 UTC, ví dụ 2026-11-23T10:15:30.123Z."""
    dt = datetime.fromtimestamp(time.time() if ts is None else ts, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ServerClient:
    def __init__(self, base_url=cfg.API_URL, device_id=cfg.DEVICE_ID,
                 queue_path=cfg.QUEUE_FILE, timeout=cfg.HTTP_TIMEOUT_S,
                 retry_interval=cfg.SEND_RETRY_INTERVAL_S,
                 poll_interval=cfg.COMMAND_POLL_INTERVAL_S,
                 heartbeat=cfg.STATE_HEARTBEAT_S, token=cfg.API_TOKEN,
                 enabled=True, max_queue=cfg.MAX_QUEUE):
        self.base_url = (base_url or "").rstrip("/")
        self.device_id = device_id
        self.queue_path = queue_path
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.poll_interval = poll_interval
        self.heartbeat = heartbeat
        self.token = token
        self.max_queue = max_queue
        self.enabled = bool(enabled and self.base_url)

        self.online = None              # None: chưa biết; True/False: lần gửi gần nhất
        self.sent_events = 0
        self._queue = deque()
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._state = None
        self._state_dirty = False
        self._state_sent_at = float("-inf")
        self._reset_seq = None
        self._pending_reset = False
        self._retry_after = 0.0
        self._next_poll = 0.0
        if self.enabled:
            self._load_queue()

    # ------------------------------------------------------------ công khai
    def start(self):
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="server-client", daemon=True)
        self._thread.start()

    def send_event(self, total=None, delta=1, ts=None):
        """Đưa một lượt vào hàng đợi (không chặn). Trả về sự kiện, hoặc None nếu tắt."""
        if not self.enabled:
            return None
        ev = {"event_id": uuid.uuid4().hex, "device_id": self.device_id,
              "timestamp": iso_utc(ts), "type": "pass", "delta": delta, "total": total}
        with self._lock:
            self._queue.append(ev)
            while len(self._queue) > self.max_queue:
                self._queue.popleft()
                log.error("Hàng đợi đầy, bỏ sự kiện cũ nhất")
            self._append_file(ev)
        self._wake.set()
        return ev

    def send_state(self, occupied, ts=None):
        """Ghi nhận trạng thái phòng mới nhất để gửi (chỉ cần bản mới nhất)."""
        if not self.enabled:
            return
        with self._lock:
            self._state = {"device_id": self.device_id, "timestamp": iso_utc(ts),
                           "occupied": bool(occupied),
                           "state": "occupied" if occupied else "empty"}
            self._state_dirty = True
        self._wake.set()

    def consume_reset(self):
        """True một lần nếu web vừa bấm reset kể từ lần gọi trước."""
        with self._lock:
            pending, self._pending_reset = self._pending_reset, False
            return pending

    @property
    def pending(self):
        with self._lock:
            return len(self._queue)

    def close(self, join_timeout=3.0):
        """Dừng luồng nền. Sự kiện chưa gửi được vẫn còn trong file để gửi lần sau."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            self._thread = None

    # ------------------------------------------------------------ luồng nền
    def _run(self):
        wait = max(0.05, min(self.poll_interval, self.retry_interval))
        while not self._stop.is_set():
            self._wake.wait(timeout=wait)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self._cycle()
            except Exception:                     # luồng nền không bao giờ được chết
                log.exception("Lỗi không mong đợi trong luồng gửi dữ liệu")
                self._retry_after = time.monotonic() + self.retry_interval

    def _cycle(self):
        now = time.monotonic()
        if now < self._retry_after:
            return
        ok = self._flush_events()
        if ok:
            ok = self._send_state_if_needed(now)
        if ok and now >= self._next_poll:
            ok = self._poll()
            self._next_poll = now + self.poll_interval
        self._set_online(ok)
        if not ok:
            self._retry_after = now + self.retry_interval

    def _set_online(self, ok):
        if ok and self.online is False:
            log.info("Đã kết nối lại server; còn %d sự kiện chờ gửi", self.pending)
        elif not ok and self.online is not False:
            log.warning("Mất kết nối server; lưu hàng đợi, sẽ gửi bù (%d sự kiện chờ)", self.pending)
        self.online = ok

    def _flush_events(self):
        sent = 0
        ok = True
        while True:
            with self._lock:
                if not self._queue:
                    break
                ev = self._queue[0]
            try:
                self._request("POST", cfg.API_EVENTS_PATH, ev)
            except urllib.error.HTTPError as exc:
                if 400 <= exc.code < 500 and exc.code not in (408, 429):
                    log.error("Server từ chối sự kiện %s (HTTP %s), bỏ qua", ev["event_id"], exc.code)
                else:
                    ok = False
                    break
            except (urllib.error.URLError, OSError, ValueError):
                ok = False
                break
            with self._lock:
                if self._queue and self._queue[0] is ev:
                    self._queue.popleft()
            sent += 1
        self.sent_events += sent
        if sent:
            with self._lock:
                self._rewrite_file()
        return ok

    def _send_state_if_needed(self, now):
        with self._lock:
            state = dict(self._state) if self._state else None
            due = self._state_dirty or (now - self._state_sent_at) >= self.heartbeat
        if state is None or not due:
            return True
        try:
            self._request("POST", cfg.API_STATE_PATH, state)
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                log.error("Server từ chối trạng thái (HTTP %s)", exc.code)
                with self._lock:
                    self._state_dirty = False
                self._state_sent_at = now
                return True
            return False
        except (urllib.error.URLError, OSError, ValueError):
            return False
        with self._lock:
            if self._state == state:            # chưa có trạng thái mới hơn trong lúc gửi
                self._state_dirty = False
        self._state_sent_at = now
        return True

    def _poll(self):
        path = f"{cfg.API_STATUS_PATH}?{urllib.parse.urlencode({'device_id': self.device_id})}"
        try:
            data = self._request("GET", path)
        except urllib.error.HTTPError as exc:
            return 400 <= exc.code < 500            # lỗi phía server cấu hình: đừng coi là mất mạng
        except (urllib.error.URLError, OSError, ValueError):
            return False
        seq = data.get("reset_seq") if isinstance(data, dict) else None
        if seq is not None:
            with self._lock:
                if self._reset_seq is None:
                    self._reset_seq = seq
                elif seq != self._reset_seq:
                    self._reset_seq = seq
                    self._pending_reset = True
        return True

    # ------------------------------------------------------------------ HTTP
    def _request(self, method, path, payload=None):
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read()
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            return {}

    # ------------------------------------------------------- hàng đợi ra file
    def _load_queue(self):
        try:
            with open(self.queue_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._queue.append(json.loads(line))
                    except ValueError:
                        log.warning("Bỏ dòng hỏng trong %s", self.queue_path)
        except FileNotFoundError:
            return
        if self._queue:
            log.info("Nạp %d sự kiện chưa gửi từ %s", len(self._queue), self.queue_path)

    def _append_file(self, ev):
        try:
            os.makedirs(os.path.dirname(self.queue_path) or ".", exist_ok=True)
            with open(self.queue_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev) + "\n")
        except OSError as exc:
            log.error("Không ghi được hàng đợi ra file: %s", exc)

    def _rewrite_file(self):
        try:
            os.makedirs(os.path.dirname(self.queue_path) or ".", exist_ok=True)
            tmp = self.queue_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for ev in self._queue:
                    f.write(json.dumps(ev) + "\n")
            os.replace(tmp, self.queue_path)
        except OSError as exc:
            log.error("Không cập nhật được file hàng đợi: %s", exc)
