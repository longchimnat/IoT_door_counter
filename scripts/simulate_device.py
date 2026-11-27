#!/usr/bin/env python3
"""Giả lập Raspberry Pi của đề tài 2 để test backend khi chưa có phần cứng.

Chế độ HTTP (mặc định) chỉ dùng thư viện chuẩn Python -> chạy được ngay trên Pi, có thể tham khảo để viết pi/client.py.
  python scripts/simulate_device.py --url http://localhost:8000 --api-key dev-door-01-key-change-me

Chế độ MQTT (cần: pip install paho-mqtt):
  python scripts/simulate_device.py --mqtt --mqtt-host localhost --mqtt-user iot --mqtt-pass iot123 --device-uid door-01 --api-key ...

Nạp dữ liệu mẫu cho cả ngày hôm nay rồi thoát (để xem biểu đồ):
  python scripts/simulate_device.py --backfill 120

Hành vi giả lập:
- Ngẫu nhiên có người đi qua cửa (trung bình --rate lượt/phút), mỗi lượt có event_id UUID.
- Thỉnh thoảng sinh 2 lần chắn cách nhau < 1s -> phía "Pi" tự gộp làm 1 lượt (đúng yêu cầu đề).
- PIR: có chuyển động khi có người; quá --empty-after giây không có chuyển động -> phòng trống.
- Mỗi --interval giây gửi telemetry; mất mạng thì giữ lượt trong hàng đợi và gửi bù sau.
- Nhận lệnh reset_counter -> đặt số đếm local về 0 và gửi ack.
"""
from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

VN = timezone(timedelta(hours=7))


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HttpTransport:
    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.timeout = timeout

    def _req(self, method: str, path: str, body: dict | None = None) -> dict | list:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("X-API-Key", self.key)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode() or "null")

    def telemetry(self, body: dict) -> dict:
        return self._req("POST", "/api/v1/telemetry", body)  # type: ignore[return-value]

    def passages(self, events: list[dict]) -> dict:
        return self._req("POST", "/api/v1/passages", {"events": events})  # type: ignore[return-value]

    def ack(self, command_id: int, status: str, detail: str | None = None) -> None:
        self._req("POST", f"/api/v1/device/commands/{command_id}/ack", {"status": status, "detail": detail})

    def state(self) -> dict:
        return self._req("GET", "/api/v1/device/state")  # type: ignore[return-value]


class SimDevice:
    def __init__(self, args):
        self.args = args
        self.local_count = 0
        self.queue: list[dict] = []  # lượt chưa gửi được (mất mạng)
        self.last_motion: float | None = None
        self.last_block: float = 0.0
        self.running = True

    # ---------- "cảm biến" ----------
    def maybe_passage(self, dt: float) -> None:
        p = self.args.rate / 60.0 * dt
        if random.random() < p:
            now = time.time()
            self.last_motion = now
            if now - self.last_block < 1.0:
                print("  (2 lần chắn < 1s -> bỏ qua, không đếm trùng)")
                return
            self.last_block = now
            self.local_count += 1
            baseline = round(random.uniform(110, 130), 1)
            ev = {
                "event_id": str(uuid.uuid4()),
                "occurred_at": iso_now(),
                "min_distance_cm": round(random.uniform(25, 70), 1),
                "baseline_cm": baseline,
                "duration_ms": random.randint(250, 900),
            }
            self.queue.append(ev)
            print(f"[{datetime.now(VN):%H:%M:%S}] +1 lượt (LCD: {self.local_count})")
            if random.random() < 0.08:  # thỉnh thoảng một lần chắn dội ngay sau đó
                self.last_block = time.time()
        elif random.random() < 0.02 * dt:
            self.last_motion = time.time()  # chuyển động trong phòng (PIR) không qua cửa

    def room_occupied(self) -> bool:
        return self.last_motion is not None and time.time() - self.last_motion < self.args.empty_after

    def telemetry_body(self) -> dict:
        return {
            "recorded_at": iso_now(),
            "room_occupied": self.room_occupied(),
            "motion": self.last_motion is not None and time.time() - self.last_motion < 3,
            "last_motion_at": datetime.fromtimestamp(self.last_motion, timezone.utc).isoformat() if self.last_motion else None,
            "distance_cm": round(random.uniform(115, 125), 1),
            "local_count": self.local_count,
        }

    # ---------- lệnh từ server ----------
    def handle_commands(self, cmds: list[dict], ack) -> None:
        for c in cmds:
            if c.get("command") == "reset_counter":
                self.local_count = 0
                print(f"[{datetime.now(VN):%H:%M:%S}] << Nhận lệnh reset #{c['id']} -> LCD về 0")
                try:
                    ack(c["id"], "success", "LCD đã về 0")
                except Exception as e:
                    print("  ack lỗi:", e)


def run_http(args) -> None:
    t = HttpTransport(args.url, args.api_key)
    dev = SimDevice(args)
    try:
        st = t.state()
        dev.local_count = st["count_today"]
        print(f"Kết nối OK: {st['name']} ({st['device_uid']}) - số đếm hôm nay trên server: {st['count_today']}")
    except Exception as e:
        print("Chưa kết nối được server:", e)

    last_tel = 0.0
    tick = 0.5
    while dev.running:
        dev.maybe_passage(tick)
        now = time.time()
        send_tel = now - last_tel >= args.interval
        if dev.queue or send_tel:
            batch = dev.queue[: 200]
            try:
                if send_tel:
                    res = t.telemetry({**dev.telemetry_body(), "passages": batch})
                    last_tel = now
                else:
                    res = t.passages(batch)
                del dev.queue[: len(batch)]
                if res.get("duplicates"):
                    print(f"  server báo {res['duplicates']} lượt trùng (gửi bù) - bỏ qua")
                dev.handle_commands(res.get("pending_commands", []), t.ack)
                if res["count_today"] != dev.local_count:
                    dev.local_count = res["count_today"]  # đồng bộ theo số chuẩn của server
            except urllib.error.HTTPError as e:  # server trả lỗi (sai API key, dữ liệu sai...)
                print("  HTTP lỗi", e.code, e.read().decode(errors="replace"))
                if e.code == 401:
                    sys.exit("Sai API key - kiểm tra --api-key")
                if e.code == 422:
                    del dev.queue[: len(batch)]  # dữ liệu hỏng, bỏ để không kẹt hàng đợi
                time.sleep(2)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                print(f"  mất kết nối ({e.__class__.__name__}) - đang giữ {len(dev.queue)} lượt để gửi bù")
                last_tel = now if send_tel else last_tel
                time.sleep(2)
        time.sleep(tick)


def run_mqtt(args) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        sys.exit("Cần cài paho-mqtt: pip install paho-mqtt")

    dev = SimDevice(args)
    p = f"{args.topic_prefix}/{args.device_uid}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{args.device_uid}")
    if args.mqtt_user:
        client.username_pw_set(args.mqtt_user, args.mqtt_pass)
    client.will_set(f"{p}/status", "offline", qos=1, retain=True)

    def ack(cid, status, detail=None):
        client.publish(f"{p}/control/ack", json.dumps({"api_key": args.api_key, "command_id": cid, "status": status, "detail": detail}), qos=1)

    def on_connect(c, _u, _f, rc, _props=None):
        print("MQTT connected rc =", rc)
        c.subscribe(f"{p}/control", qos=1)
        c.subscribe(f"{p}/sync", qos=0)
        c.publish(f"{p}/status", "online", qos=1, retain=True)

    def on_message(_c, _u, msg):
        body = json.loads(msg.payload.decode())
        if msg.topic.endswith("/control"):
            dev.handle_commands([body], ack)
        elif msg.topic.endswith("/sync"):
            dev.local_count = body.get("count_today", dev.local_count)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.mqtt_host, args.mqtt_port, keepalive=30)
    client.loop_start()
    last_tel = 0.0
    try:
        while dev.running:
            dev.maybe_passage(0.5)
            now = time.time()
            if dev.queue or now - last_tel >= args.interval:
                body = {**dev.telemetry_body(), "passages": dev.queue[:200], "api_key": args.api_key}
                info = client.publish(f"{p}/telemetry", json.dumps(body), qos=1)
                if info.rc == mqtt.MQTT_ERR_SUCCESS:
                    del dev.queue[: len(body["passages"])]
                    last_tel = now
            time.sleep(0.5)
    finally:
        client.publish(f"{p}/status", "offline", qos=1, retain=True)
        client.loop_stop()
        client.disconnect()


def backfill(args) -> None:
    """Nạp N lượt rải từ 7h sáng tới hiện tại hôm nay (dữ liệu demo biểu đồ)."""
    t = HttpTransport(args.url, args.api_key)
    now = datetime.now(VN)
    start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if now <= start:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    span = (now - start).total_seconds()
    # mật độ cao vào giờ ra/vào lớp
    times = sorted(start + timedelta(seconds=random.triangular(0, span, span * 0.35)) for _ in range(args.backfill))
    events = [
        {"event_id": str(uuid.uuid4()), "occurred_at": ts.isoformat(), "min_distance_cm": round(random.uniform(25, 70), 1),
         "baseline_cm": 120.0, "duration_ms": random.randint(250, 900)}
        for ts in times
    ]
    total = 0
    for i in range(0, len(events), 200):
        res = t.passages(events[i:i + 200])
        total += res["accepted"]
    print(f"Đã nạp {total}/{len(events)} lượt (một số bị server gộp vì cách nhau < 1s). Hôm nay: {res['count_today']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Giả lập Raspberry Pi - đề tài 2")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--api-key", default="dev-door-01-key-change-me")
    ap.add_argument("--device-uid", default="door-01")
    ap.add_argument("--rate", type=float, default=6.0, help="số lượt trung bình mỗi phút")
    ap.add_argument("--interval", type=float, default=10.0, help="chu kỳ gửi telemetry (giây)")
    ap.add_argument("--empty-after", type=float, default=300.0, help="PIR: số giây không chuyển động -> phòng trống")
    ap.add_argument("--backfill", type=int, default=0, help="nạp N lượt mẫu cho hôm nay rồi thoát")
    ap.add_argument("--mqtt", action="store_true")
    ap.add_argument("--mqtt-host", default="localhost")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--mqtt-user", default=None)
    ap.add_argument("--mqtt-pass", default=None)
    ap.add_argument("--topic-prefix", default="iot/devices")
    args = ap.parse_args()

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    if args.backfill:
        backfill(args)
    elif args.mqtt:
        run_mqtt(args)
    else:
        run_http(args)


if __name__ == "__main__":
    main()
