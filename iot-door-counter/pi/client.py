"""[Leader / Người D] Gửi dữ liệu lên server, nhận lệnh. Chạy luồng nền để không làm đứng vòng đo.
Định dạng JSON xem docs/API.md.
"""
import datetime
import queue
import threading
import time

import requests

from . import config


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class ApiClient:
    def __init__(self, api_url=config.API_URL, device_id=config.DEVICE_ID):
        self.api_url = api_url.rstrip("/")
        self.device_id = device_id
        self._q = queue.Queue(maxsize=1000)
        threading.Thread(target=self._worker, daemon=True).start()

    def send_event(self, event_type, **fields):
        payload = {"device_id": self.device_id, "timestamp": _now_iso(),
                   "type": event_type, **fields}
        try:
            self._q.put_nowait(payload)
        except queue.Full:
            print("[client] hàng đợi đầy, bỏ sự kiện")

    def _worker(self):
        while True:
            payload = self._q.get()
            while True:   # thử lại tới khi gửi được (mất mạng không mất dữ liệu)
                try:
                    r = requests.post(f"{self.api_url}/api/events", json=payload, timeout=3)
                    if r.status_code < 500:
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)

    def fetch_commands(self):
        """Trả về list lệnh, ví dụ [{"id": 3, "type": "reset"}]. Lỗi mạng => []."""
        try:
            r = requests.get(f"{self.api_url}/api/commands",
                             params={"device_id": self.device_id}, timeout=3)
            r.raise_for_status()
            return r.json().get("commands", [])
        except (requests.RequestException, ValueError):
            return []
