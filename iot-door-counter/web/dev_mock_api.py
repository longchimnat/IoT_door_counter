"""[Người E] API giả để thử web khi server của D chưa xong. CHỈ DÙNG KHI PHÁT TRIỂN.

Chạy:  python web/dev_mock_api.py        rồi mở http://localhost:5000
Làm đúng theo docs/API.md. Mỗi ~4 giây tự sinh 1 lượt ngẫu nhiên, trạng thái phòng đổi ngẫu nhiên,
để thấy biểu đồ và thẻ trạng thái cập nhật. Chỉ dùng thư viện chuẩn của Python.
Khi server thật (server/app.py) chạy được thì không cần file này nữa.
"""
import json
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VN = timezone(timedelta(hours=7))
INDEX = Path(__file__).with_name("index.html")
lock = threading.Lock()

events = []            # (datetime UTC, ...) mỗi phần tử là 1 lượt
state = {"room": "empty", "last": datetime.now(timezone.utc), "reset_at": None}

# dữ liệu mẫu cho hôm nay (các giờ đã qua) và hôm qua
now = datetime.now(VN)
for day_offset in (0, 1):
    for h in range(7, 22):
        t = (now - timedelta(days=day_offset)).replace(hour=h, minute=0, second=0, microsecond=0)
        if day_offset == 0 and t > now:
            continue
        weight = {8: 14, 12: 18, 13: 10, 17: 16}.get(h, 4)
        for _ in range(random.randint(weight // 2, weight)):
            ev = min(t + timedelta(minutes=random.randint(0, 59)), now - timedelta(minutes=1))
            events.append(ev.astimezone(timezone.utc))


def count_today():
    d0 = datetime.now(VN).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    since = max(d0, state["reset_at"]) if state["reset_at"] else d0
    return sum(1 for e in events if e >= since)


def simulate():
    while True:
        time.sleep(4)
        with lock:
            if random.random() < 0.6:
                events.append(datetime.now(timezone.utc))
                state["last"] = datetime.now(timezone.utc)
            if random.random() < 0.15:
                state["room"] = "empty" if state["room"] == "occupied" else "occupied"
                state["last"] = datetime.now(timezone.utc)


class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        with lock:
            if u.path == "/":
                body = INDEX.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/health":
                self._json({"ok": True})
            elif u.path == "/api/status":
                self._json({"count_today": count_today(), "room_status": state["room"],
                            "last_update": state["last"].isoformat()})
            elif u.path == "/api/stats/hourly":
                date = q.get("date", [datetime.now(VN).strftime("%Y-%m-%d")])[0]
                try:
                    d0 = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=VN)
                except ValueError:
                    return self._json({"error": "date sai định dạng"}, 400)
                hours = [{"hour": h, "count": 0} for h in range(24)]
                for e in events:
                    local = e.astimezone(VN)
                    if local.date() == d0.date():
                        hours[local.hour]["count"] += 1
                self._json({"date": date, "hours": hours})
            elif u.path == "/api/commands":
                self._json({"commands": []})
            else:
                self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        with lock:
            if u.path == "/api/reset":
                state["reset_at"] = datetime.now(timezone.utc)
                state["last"] = state["reset_at"]
                self._json({"ok": True}, 201)
            else:
                self._json({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=simulate, daemon=True).start()
    print("API giả chạy tại http://localhost:5000  (Ctrl+C để dừng)")
    ThreadingHTTPServer(("0.0.0.0", 5000), H).serve_forever()
