"""Test backend đề tài 2. Chạy: pytest -q"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def ev(ts: datetime, event_id: str | None = None, **kw) -> dict:
    return {"event_id": event_id or str(uuid.uuid4()), "occurred_at": ts.isoformat(), **kw}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def send(client, dev, *events):
    r = client.post("/api/v1/passages", json={"events": list(events)}, headers=dev)
    assert r.status_code == 200, r.text
    return r.json()


def summary(client, auth, device_id):
    r = client.get("/api/v1/stats/summary", params={"device_id": device_id}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- Cơ bản ----------------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] is True


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_login_and_protected(client, auth):
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "sai"}).status_code == 401
    assert client.get("/api/v1/devices").status_code == 401
    assert client.get("/api/v1/devices", headers={"Authorization": "Bearer abc"}).status_code == 401
    r = client.get("/api/v1/auth/me", headers=auth)
    assert r.status_code == 200 and r.json()["username"] == "admin"


def test_device_crud(client, auth):
    r = client.post("/api/v1/devices", json={"device_uid": "door-02", "name": "Cửa phòng A2"}, headers=auth)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["api_key"] and d["status"] == "unknown"
    assert client.post("/api/v1/devices", json={"device_uid": "door-02", "name": "x"}, headers=auth).status_code == 409
    assert client.post("/api/v1/devices", json={"device_uid": "bad uid!", "name": "x"}, headers=auth).status_code == 422

    r = client.patch(f"/api/v1/devices/{d['id']}", json={"location": "Tầng 2"}, headers=auth)
    assert r.json()["location"] == "Tầng 2"
    old_key = d["api_key"]
    new_key = client.post(f"/api/v1/devices/{d['id']}/rotate-key", headers=auth).json()["api_key"]
    assert new_key != old_key
    assert client.get("/api/v1/device/state", headers={"X-API-Key": old_key}).status_code == 401
    assert client.get("/api/v1/device/state", headers={"X-API-Key": new_key}).status_code == 200

    assert client.delete(f"/api/v1/devices/{d['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/devices/{d['id']}", headers=auth).status_code == 404


# ---------------- Đếm lượt ----------------
def test_device_auth_required(client):
    body = {"events": [ev(now_utc())]}
    assert client.post("/api/v1/passages", json=body).status_code == 401
    assert client.post("/api/v1/passages", json=body, headers={"X-API-Key": "wrong"}).status_code == 401


def test_count_passages(client, auth, dev, device_id):
    t = now_utc() - timedelta(seconds=30)
    res = send(client, dev, ev(t), ev(t + timedelta(seconds=3)), ev(t + timedelta(seconds=6)))
    assert res["accepted"] == 3 and res["count_today"] == 3
    s = summary(client, auth, device_id)
    assert s["count_today"] == 3
    assert s["device"]["status"] == "online"


def test_duplicate_event_id_resend(client, auth, dev, device_id):
    """Kịch bản 10: mất Wi-Fi rồi gửi bù -> không đếm trùng."""
    t = now_utc() - timedelta(seconds=60)
    e1, e2 = ev(t), ev(t + timedelta(seconds=5))
    send(client, dev, e1)
    res = send(client, dev, e1, e2)  # gửi bù cả batch
    assert res["accepted"] == 1 and res["duplicates"] == 1 and res["count_today"] == 2
    res = send(client, dev, e2, e2)
    assert res["accepted"] == 0 and res["duplicates"] == 2


def test_server_debounce_under_1s(client, dev):
    """Kịch bản 4: hai lần chắn cách nhau < 1 giây chỉ tính 1 lượt."""
    t = now_utc() - timedelta(seconds=20)
    res = send(client, dev, ev(t), ev(t + timedelta(milliseconds=400)), ev(t + timedelta(milliseconds=1500)))
    assert res["accepted"] == 2 and res["debounced"] == 1
    res = send(client, dev, ev(t + timedelta(milliseconds=1700)))  # sát lượt đã lưu
    assert res["accepted"] == 0 and res["debounced"] == 1


def test_naive_timestamp_is_local_time(client, auth, dev, device_id):
    local_now = now_utc().astimezone(VN).replace(minute=0, second=1, microsecond=0, tzinfo=None)
    send(client, dev, {"event_id": "naive-1", "occurred_at": local_now.isoformat()})
    r = client.get("/api/v1/stats/hourly", params={"device_id": device_id}, headers=auth).json()
    assert r["buckets"][local_now.hour]["count"] == 1


def test_yesterday_not_counted_today(client, auth, dev, device_id):
    send(client, dev, ev(now_utc() - timedelta(days=1, hours=1)), ev(now_utc() - timedelta(minutes=1)))
    assert summary(client, auth, device_id)["count_today"] == 1


def test_batch_limit(client, dev, monkeypatch):
    from server.config import get_settings

    monkeypatch.setattr(get_settings(), "max_batch_size", 2)
    t = now_utc()
    body = {"events": [ev(t - timedelta(seconds=i * 2)) for i in range(3)]}
    assert client.post("/api/v1/passages", json=body, headers=dev).status_code == 413


def test_validation_error(client, dev):
    r = client.post("/api/v1/passages", json={"events": [{"event_id": "x", "occurred_at": "not-a-date"}]}, headers=dev)
    assert r.status_code == 422
    assert client.post("/api/v1/passages", json={"events": []}, headers=dev).status_code == 422


# ---------------- Reset ----------------
def test_reset_flow(client, auth, dev, device_id):
    t = now_utc() - timedelta(seconds=40)
    send(client, dev, ev(t), ev(t + timedelta(seconds=5)))

    r = client.post(f"/api/v1/devices/{device_id}/control", json={"command": "reset_counter"}, headers=auth)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["count_today"] == 0 and "http_poll" in body["delivered_via"]
    cmd_id = body["command"]["id"]

    # Pi nhận lệnh trong response telemetry kế tiếp
    tel = client.post("/api/v1/telemetry", json={"room_occupied": True, "motion": True, "local_count": 2}, headers=dev).json()
    assert [c["id"] for c in tel["pending_commands"]] == [cmd_id]
    assert tel["pending_commands"][0]["command"] == "reset_counter"
    assert tel["count_today"] == 0

    # lượt cũ gửi bù (xảy ra trước reset) không làm tăng số sau reset
    res = send(client, dev, ev(t + timedelta(seconds=10)))
    assert res["accepted"] == 1 and res["count_today"] == 0

    # ack
    r = client.post(f"/api/v1/device/commands/{cmd_id}/ack", json={"status": "success"}, headers=dev)
    assert r.status_code == 200 and r.json()["status"] == "success"
    assert client.get("/api/v1/device/commands", headers=dev).json() == []

    # lượt mới sau reset
    res = send(client, dev, ev(now_utc()))
    assert res["count_today"] == 1
    s = summary(client, auth, device_id)
    assert s["count_today"] == 1 and s["total_today_before_reset"] == 4 and s["last_reset_at"]

    h = client.get("/api/v1/stats/hourly", params={"device_id": device_id}, headers=auth).json()
    assert h["total"] == 1
    h_all = client.get("/api/v1/stats/hourly", params={"device_id": device_id, "since_reset": False}, headers=auth).json()
    assert h_all["total"] == 4

    logs = client.get(f"/api/v1/devices/{device_id}/control-logs", headers=auth).json()
    assert logs[0]["triggered_by"] == "admin" and logs[0]["status"] == "success"


def test_reset_supersedes_and_ack_failed_alert(client, auth, dev, device_id):
    c1 = client.post(f"/api/v1/devices/{device_id}/reset", headers=auth).json()["command"]["id"]
    c2 = client.post(f"/api/v1/devices/{device_id}/reset", headers=auth).json()["command"]["id"]
    pending = client.get("/api/v1/device/commands", headers=dev).json()
    assert [c["id"] for c in pending] == [c2]
    assert client.post(f"/api/v1/device/commands/{c1}/ack", json={"status": "success"}, headers=dev).status_code == 200
    r = client.post(f"/api/v1/device/commands/{c2}/ack", json={"status": "failed", "detail": "LCD lỗi"}, headers=dev)
    assert r.json()["status"] == "failed"
    alerts = client.get("/api/v1/alerts", params={"device_id": device_id, "resolved": False}, headers=auth).json()
    assert alerts[0]["alert_type"] == "command_failed"
    assert client.post(f"/api/v1/device/commands/{c2}/ack", json={"status": "pending"}, headers=dev).status_code == 422
    assert client.post("/api/v1/device/commands/9999/ack", json={"status": "success"}, headers=dev).status_code == 404
    r = client.post(f"/api/v1/alerts/{alerts[0]['id']}/resolve", headers=auth)
    assert r.json()["is_resolved"] is True


# ---------------- Trạng thái phòng / thiết bị ----------------
def test_telemetry_room_state_and_history(client, auth, dev, device_id):
    motion_at = now_utc() - timedelta(minutes=1)
    r = client.post(
        "/api/v1/telemetry",
        json={"room_occupied": True, "motion": True, "last_motion_at": motion_at.isoformat(), "distance_cm": 85.2,
              "local_count": 0, "passages": [ev(now_utc() - timedelta(seconds=5))]},
        headers=dev,
    )
    assert r.status_code == 200 and r.json()["accepted"] == 1
    client.post("/api/v1/telemetry", json={"room_occupied": False, "motion": False, "distance_cm": 120}, headers=dev)

    d = client.get(f"/api/v1/devices/{device_id}", headers=auth).json()
    assert d["room_occupied"] is False and d["last_distance_cm"] == 120 and d["status"] == "online"
    hist = client.get("/api/v1/telemetry/history", params={"device_id": device_id}, headers=auth).json()
    assert [h["room_occupied"] for h in hist] == [True, False]

    state = client.get("/api/v1/device/state", headers=dev).json()
    assert state["count_today"] == 1


def test_offline_detection(client, auth, dev, device_id):
    from sqlalchemy import update

    from server.database import get_sessionmaker
    from server.models import Device
    from server.services.device_service import check_offline_once

    client.post("/api/v1/telemetry", json={"room_occupied": False}, headers=dev)

    async def age_and_check():
        async with get_sessionmaker()() as s:
            await s.execute(update(Device).where(Device.id == device_id).values(last_ping=now_utc() - timedelta(hours=1)))
            await s.commit()
        return await check_offline_once()

    assert client.portal.call(age_and_check) == 1
    assert client.get(f"/api/v1/devices/{device_id}", headers=auth).json()["status"] == "offline"
    alerts = client.get("/api/v1/alerts", params={"resolved": False}, headers=auth).json()
    assert alerts and alerts[0]["alert_type"] == "device_offline"

    client.post("/api/v1/telemetry", json={"room_occupied": False}, headers=dev)
    assert client.get(f"/api/v1/devices/{device_id}", headers=auth).json()["status"] == "online"
    assert client.get("/api/v1/alerts", params={"resolved": False}, headers=auth).json() == []


# ---------------- Thống kê / xuất file ----------------
def test_hourly_and_daily(client, auth, dev, device_id):
    today = now_utc().astimezone(VN).date()
    base = datetime(today.year, today.month, today.day, tzinfo=VN)
    cur_hour = now_utc().astimezone(VN).hour
    events = [ev(base + timedelta(hours=0, minutes=5))]
    if cur_hour >= 1:
        events += [ev(base + timedelta(hours=1, minutes=m)) for m in (1, 2, 3)]
    send(client, dev, *events)
    h = client.get("/api/v1/stats/hourly", params={"device_id": device_id, "date": today.isoformat()}, headers=auth).json()
    assert len(h["buckets"]) == 24 and h["buckets"][0]["count"] == 1
    assert h["total"] == len(events)
    if cur_hour >= 1:
        assert h["buckets"][1]["count"] == 3

    d = client.get("/api/v1/stats/daily", params={"device_id": device_id, "days": 7}, headers=auth).json()
    assert len(d["days"]) == 7 and d["days"][-1]["count"] == len(events)


def test_list_and_export_csv(client, auth, dev, device_id):
    t = now_utc() - timedelta(minutes=10)
    send(client, dev, ev(t, "e-1", min_distance_cm=40.5, baseline_cm=120), ev(t + timedelta(seconds=10), "e-2"))
    page = client.get("/api/v1/passages", params={"device_id": device_id}, headers=auth).json()
    assert page["total"] == 2 and page["items"][0]["event_uid"] == "e-2"

    r = client.get("/api/v1/passages/export.csv", params={"device_id": device_id}, headers=auth)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    lines = r.content.decode("utf-8-sig").strip().splitlines()
    assert lines[0].startswith("stt,thoi_gian") and len(lines) == 3 and "e-1" in lines[1]

    bad = client.get("/api/v1/passages", params={"device_id": device_id, "from": "2026-01-02T00:00:00", "to": "2026-01-01T00:00:00"}, headers=auth)
    assert bad.status_code == 422


# ---------------- WebSocket ----------------
def test_websocket_push(client, auth, token, dev, device_id):
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_text("ping")
        assert ws.receive_text() == "pong"
        send(client, dev, ev(now_utc()))
        msgs = [ws.receive_json() for _ in range(2)]  # device_status (online) + passage
        types = {m["type"] for m in msgs}
        assert "passage" in types
        passage = next(m for m in msgs if m["type"] == "passage")
        assert passage["device_id"] == device_id and passage["data"]["count_today"] == 1

        client.post(f"/api/v1/devices/{device_id}/reset", headers=auth)
        got = [ws.receive_json()["type"] for _ in range(2)]
        assert "counter_reset" in got


def test_websocket_rejects_bad_token(client):
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect("/ws?token=bad") as ws:
            ws.receive_text()
        raise AssertionError("phải bị từ chối")
    except WebSocketDisconnect as e:
        assert e.code == 1008


def test_mqtt_handler_without_broker(client, auth, device_id):
    """Kiểm tra logic xử lý message MQTT (không cần broker thật)."""
    import json

    from server.mqtt.bridge import bridge

    payload = {"api_key": "test-device-key", "room_occupied": True, "passages": [ev(now_utc(), "mqtt-1")]}

    async def run():
        await bridge._handle("iot/devices/door-01/telemetry", json.dumps(payload).encode())
        await bridge._handle("iot/devices/door-01/telemetry", json.dumps({**payload, "api_key": "sai"}).encode())
        await bridge._handle("iot/devices/unknown/telemetry", json.dumps(payload).encode())
        await bridge._handle("iot/devices/door-01/status", b"offline")

    client.portal.call(run)
    s = summary(client, auth, device_id)
    assert s["count_today"] == 1
    assert s["device"]["status"] == "offline" and s["device"]["room_occupied"] is True
