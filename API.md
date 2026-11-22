# API & định dạng dữ liệu – Đề tài 2: Đếm lượt người qua cửa

> Hợp đồng giữa **Pi** (`pi/client.py` – Long), **thuật toán đếm** (Huệ), **backend** (Hiệp) và **web** (Mai Phương).
> Không đổi tên trường / đường dẫn khi chưa báo leader.
> Swagger đầy đủ (thử API trực tiếp trên trình duyệt): `http://<IP-server>:8000/docs`

- Base URL: `http://<IP-server>:8000`
- Thời gian: chuỗi **ISO-8601**. Có múi giờ (`...Z` hoặc `+07:00`) thì dùng đúng múi đó; **không có múi giờ thì server hiểu là giờ Việt Nam**. Server luôn trả về UTC (`...Z`).
- Ngày / giờ trong thống kê tính theo `Asia/Ho_Chi_Minh`.
- Trên Windows PowerShell dùng `curl.exe` (không phải `curl`) để chạy các lệnh mẫu.

## 1. Xác thực

| Ai gọi | Cách xác thực |
|---|---|
| Raspberry Pi | Header `X-API-Key: <api_key của thiết bị>` (thiết bị mặc định `door-01` dùng `DEFAULT_DEVICE_API_KEY` trong `.env`) |
| Dashboard / người dùng | `POST /api/v1/auth/login` → header `Authorization: Bearer <access_token>` |
| WebSocket | `ws://<IP>:8000/ws?token=<access_token>` |

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
# -> {"access_token":"eyJ...","token_type":"bearer","expires_in":43200}
```

---

## 2. API cho Raspberry Pi (header `X-API-Key`)

### 2.1 `POST /api/v1/passages` – gửi lượt qua cửa

Gửi ngay khi đếm được 1 lượt, hoặc gửi bù nhiều lượt sau khi mất Wi-Fi (tối đa 500 lượt/request).

```json
{
  "events": [
    {
      "event_id": "5b0b8a8e-3c1e-4d0f-9a43-0f6f1c2d9a10",
      "occurred_at": "2026-11-18T08:15:02.120+07:00",
      "min_distance_cm": 42.5,
      "baseline_cm": 120.0,
      "duration_ms": 480
    }
  ]
}
```

| Trường | Bắt buộc | Ý nghĩa |
|---|---|---|
| `event_id` | ✔ | Chuỗi duy nhất cho mỗi lượt (`str(uuid.uuid4())`). **Gửi lại cùng `event_id` không bị đếm 2 lần** → cứ gửi bù thoải mái. |
| `occurred_at` | ✔ | Thời điểm người đi qua (lấy trên Pi, không phải lúc gửi). |
| `min_distance_cm` | | Khoảng cách nhỏ nhất khi bị chắn. |
| `baseline_cm` | | Khoảng cách nền (cửa trống) lúc đó. |
| `duration_ms` | | Thời gian bị chắn. |

Response `200`:

```json
{
  "accepted": 1,
  "duplicates": 0,
  "debounced": 0,
  "count_today": 37,
  "last_reset_at": null,
  "pending_commands": []
}
```

- `duplicates`: số lượt trùng `event_id` đã có (gửi bù) → bỏ qua.
- `debounced`: số lượt cách lượt khác **< 1 giây** → server chỉ giữ 1 (lớp bảo vệ thứ 2; Pi vẫn phải tự lọc 1 s).
- `count_today`: **số chuẩn của server** – Pi nên hiển thị số này lên LCD khi online.
- `pending_commands`: lệnh đang chờ (xem 2.4).

```bash
curl -X POST http://localhost:8000/api/v1/passages \
  -H "X-API-Key: dev-door-01-key-change-me" -H "Content-Type: application/json" \
  -d '{"events":[{"event_id":"test-0001","occurred_at":"2026-11-18T08:15:02+07:00","min_distance_cm":42.5,"baseline_cm":120}]}'
```

### 2.2 `POST /api/v1/telemetry` – nhịp định kỳ (khuyên 5–10 giây/lần)

Báo trạng thái phòng (PIR), khoảng cách hiện tại, số đếm trên LCD. Có thể kèm `passages` chưa gửi. Đồng thời là **heartbeat**: quá `DEVICE_OFFLINE_SECONDS` (90 s) không gửi gì → thiết bị bị đánh dấu offline + cảnh báo.

```json
{
  "recorded_at": "2026-11-18T08:15:10+07:00",
  "room_occupied": true,
  "motion": true,
  "last_motion_at": "2026-11-18T08:15:08+07:00",
  "distance_cm": 119.4,
  "local_count": 37,
  "extra": {"cpu_temp": 52.1},
  "passages": []
}
```

| Trường | Ý nghĩa |
|---|---|
| `room_occupied` | `true` = có người (LED đỏ); `false` = phòng trống – PIR không thấy chuyển động 5 phút (LED xanh). **Pi tự tính 5 phút**, server chỉ lưu và hiển thị. |
| `motion` | PIR đang thấy chuyển động tại thời điểm gửi. |
| `last_motion_at` | Lần cuối PIR thấy chuyển động. |
| `distance_cm` | Khoảng cách HC-SR04 đo được hiện tại. |
| `local_count` | Số lượt Pi đang hiện trên LCD (để đối chiếu). |
| `extra` | Object tùy ý (nhiệt độ CPU, RSSI...). |

Response giống 2.1.

```bash
curl -X POST http://localhost:8000/api/v1/telemetry \
  -H "X-API-Key: dev-door-01-key-change-me" -H "Content-Type: application/json" \
  -d '{"room_occupied":true,"motion":true,"distance_cm":119.4,"local_count":37}'
```

### 2.3 `GET /api/v1/device/state` – lấy số đếm khi Pi khởi động lại

```json
{"device_id":1,"device_uid":"door-01","name":"Cửa thư viện","date":"2026-11-18","count_today":37,"last_reset_at":null}
```

### 2.4 Lệnh đặt lại số đếm (reset)

Khi người dùng bấm **"Đặt lại số đếm"** trên web, Pi nhận lệnh theo 1 trong 3 cách:

1. Trong `pending_commands` của response `/passages` hoặc `/telemetry` (cách đơn giản nhất).
2. `GET /api/v1/device/commands` (poll).
3. MQTT topic `iot/devices/{device_uid}/control` (nếu bật MQTT).

Định dạng lệnh:

```json
{"id": 12, "command": "reset_counter", "payload": {}, "status": "sent", "created_at": "2026-11-18T03:20:00Z"}
```

Pi xử lý: đặt bộ đếm local = 0 (LCD hiện 0), rồi **ack**:

```bash
curl -X POST http://localhost:8000/api/v1/device/commands/12/ack \
  -H "X-API-Key: dev-door-01-key-change-me" -H "Content-Type: application/json" \
  -d '{"status":"success","detail":"LCD da ve 0"}'
```

`status` = `success` | `failed`. Lệnh chưa ack sẽ tiếp tục xuất hiện trong `pending_commands` (ack nhiều lần không sao). Nhiều lần bấm reset liên tiếp → chỉ lệnh mới nhất còn chờ.

### Quy ước reset (đã chốt)

- Server về 0 **ngay khi bấm nút** (không chờ Pi). Thời điểm reset = lúc tạo lệnh.
- `count_today` = số lượt có `occurred_at` ≥ max(0h hôm nay, lần reset gần nhất hôm nay).
- Lượt xảy ra **trước** thời điểm reset nhưng gửi bù sau → vẫn được lưu nhưng **không** cộng vào số sau reset.
- Dữ liệu cũ **không bị xóa** (dùng làm bảng số liệu test, xuất CSV).
- Qua 0h ngày mới tự về 0, không cần reset.
- Sau khi reset, Pi nên lấy `count_today` trong response kế tiếp làm số hiển thị.

### Gợi ý code phía Pi (`pi/client.py`)

```python
import json, urllib.request, uuid
from datetime import datetime, timezone

API_URL = "http://192.168.1.10:8000"      # IP máy chạy server
API_KEY = "dev-door-01-key-change-me"

def _post(path, body):
    req = urllib.request.Request(API_URL + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"X-API-Key": API_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

queue = []                                 # lượt chưa gửi được (mất mạng)

def on_passage(min_cm, base_cm, dur_ms):   # counter.py gọi khi đếm được 1 lượt
    queue.append({"event_id": str(uuid.uuid4()),
                  "occurred_at": datetime.now(timezone.utc).isoformat(),
                  "min_distance_cm": min_cm, "baseline_cm": base_cm, "duration_ms": dur_ms})

def flush(room_occupied, distance_cm, local_count):   # gọi mỗi 5-10 giây
    batch = queue[:200]
    try:
        res = _post("/api/v1/telemetry", {"room_occupied": room_occupied, "distance_cm": distance_cm,
                                           "local_count": local_count, "passages": batch})
    except OSError:
        return None                        # mất mạng: giữ queue, lần sau gửi bù
    del queue[:len(batch)]
    for cmd in res["pending_commands"]:
        if cmd["command"] == "reset_counter":
            # ... đặt bộ đếm local = 0, cập nhật LCD ...
            _post(f"/api/v1/device/commands/{cmd['id']}/ack", {"status": "success"})
    return res["count_today"]
```

Bản đầy đủ chạy được: `scripts/simulate_device.py`.

---

## 3. MQTT (tùy chọn – bật `MQTT_ENABLED=true`)

Broker: Mosquitto trong `docker-compose.yml`, cổng `1883`, tài khoản `MQTT_USERNAME`/`MQTT_PASSWORD`.
Mọi gói uplink dạng JSON phải có thêm trường `"api_key"` (server kiểm tra giống HTTP).

| Hướng | Topic | Payload |
|---|---|---|
| Pi → Server | `iot/devices/{uid}/telemetry` | Giống body 2.2 + `"api_key"`; có thể kèm `"passages": [...]` |
| Pi → Server | `iot/devices/{uid}/control/ack` | `{"api_key": "...", "command_id": 12, "status": "success", "detail": null}` |
| Pi → Server | `iot/devices/{uid}/status` | `online` / `offline` (retain). **Đặt LWT = `offline`** khi connect |
| Server → Pi | `iot/devices/{uid}/control` | Lệnh như mục 2.4 (QoS 1) |
| Server → Pi | `iot/devices/{uid}/sync` | `{"count_today": 37, "last_reset_at": null}` sau mỗi gói telemetry |

```bash
mosquitto_pub -h localhost -u iot -P iot_mqtt_password -t iot/devices/door-01/telemetry \
  -m '{"api_key":"dev-door-01-key-change-me","room_occupied":true,"passages":[{"event_id":"mq-1","occurred_at":"2026-11-18T08:00:00+07:00"}]}'
mosquitto_sub -h localhost -u iot -P iot_mqtt_password -t 'iot/devices/door-01/#' -v
```

---

## 4. API cho Dashboard (header `Authorization: Bearer <token>`)

| Method | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/api/v1/auth/login` | Đăng nhập → JWT |
| GET | `/api/v1/auth/me` | Thông tin tài khoản |
| GET | `/api/v1/devices` | Danh sách thiết bị |
| POST | `/api/v1/devices` | Thêm thiết bị `{"device_uid","name","location"}` → trả `api_key` |
| GET / PATCH / DELETE | `/api/v1/devices/{id}` | Xem (kèm api_key) / sửa tên, vị trí / xóa |
| POST | `/api/v1/devices/{id}/rotate-key` | Đổi API key |
| POST | `/api/v1/devices/{id}/control` | Gửi lệnh `{"command":"reset_counter"}` (nút **Đặt lại**) |
| POST | `/api/v1/devices/{id}/reset` | Viết tắt của lệnh trên |
| GET | `/api/v1/devices/{id}/control-logs` | Lịch sử lệnh + trạng thái |
| GET | `/api/v1/stats/summary?device_id=1` | Số lượt hôm nay, trạng thái phòng, thiết bị |
| GET | `/api/v1/stats/hourly?device_id=1&date=2026-11-18&since_reset=true` | **Biểu đồ lượt theo giờ** (24 cột) |
| GET | `/api/v1/stats/daily?device_id=1&days=7` | Tổng lượt từng ngày |
| GET | `/api/v1/passages?device_id=1&from=...&to=...&limit=100&offset=0` | Danh sách lượt (mặc định 24 h) |
| GET | `/api/v1/passages/export.csv?device_id=1&from=...&to=...` | Xuất CSV (mở bằng Excel) |
| GET | `/api/v1/telemetry/history?device_id=1&from=...&to=...` | Lịch sử trạng thái phòng / khoảng cách |
| GET | `/api/v1/alerts?device_id=1&resolved=false` | Cảnh báo (offline, lệnh lỗi) |
| POST | `/api/v1/alerts/{id}/resolve` | Đánh dấu đã xử lý |
| GET | `/health` | Kiểm tra server + DB + MQTT |

Ví dụ biểu đồ theo giờ:

```bash
TOKEN=...   # access_token
curl "http://localhost:8000/api/v1/stats/hourly?device_id=1" -H "Authorization: Bearer $TOKEN"
```

```json
{
  "device_id": 1, "date": "2026-11-18", "timezone": "Asia/Ho_Chi_Minh",
  "since_reset": true, "last_reset_at": null, "total": 37,
  "buckets": [{"hour": 0, "count": 0}, {"hour": 7, "count": 12}, {"hour": 8, "count": 25}]
}
```
(`buckets` luôn đủ 24 phần tử, ví dụ trên rút gọn.)

Bấm reset:

```bash
curl -X POST http://localhost:8000/api/v1/devices/1/control \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"command":"reset_counter"}'
# -> 202 {"command": {...,"status":"sent"}, "delivered_via": ["mqtt","http_poll"], "count_today": 0}
```

## 5. WebSocket realtime – `ws://<IP>:8000/ws?token=<JWT>`

Server đẩy: `{"type": "...", "device_id": 1, "ts": "...Z", "data": {...}}`

| `type` | Khi nào | `data` |
|---|---|---|
| `passage` | Có lượt mới | thông tin lượt + `count_today` |
| `room_state` | Mỗi gói telemetry | thông tin thiết bị + `room_changed`, `count_today`, `local_count` |
| `device_status` | Online ↔ offline | thông tin thiết bị |
| `counter_reset` | Bấm đặt lại | `count_today`, `last_reset_at`, `by` |
| `command` / `command_ack` | Tạo lệnh / Pi xác nhận | bản ghi control_logs |
| `alert` | Có cảnh báo mới / đã xử lý | bản ghi alerts |

Client gửi `ping` → server trả `pong` (giữ kết nối).

## 6. Mã lỗi

| Mã | Ý nghĩa |
|---|---|
| 401 | Thiếu / sai token hoặc API key |
| 404 | Không tìm thấy thiết bị / lệnh / cảnh báo |
| 409 | `device_uid` đã tồn tại |
| 413 | Quá 500 lượt trong 1 request → chia nhỏ |
| 422 | Dữ liệu sai định dạng (chi tiết trong `detail`) |

## 7. Cơ sở dữ liệu

| Bảng | Nội dung |
|---|---|
| `users` | Tài khoản dashboard (mật khẩu băm PBKDF2-SHA256) |
| `devices` | Thiết bị: `device_uid`, `api_key`, `status`, `last_ping`, trạng thái phòng hiện tại |
| `passage_events` | Mỗi dòng = 1 lượt. Unique (`device_id`, `event_uid`); index (`device_id`, `occurred_at`) |
| `sensor_data` | Telemetry định kỳ (PIR, khoảng cách, `local_count`) |
| `control_logs` | Lệnh reset: `status` pending → sent → success / failed / superseded, `triggered_by` |
| `alerts` | `device_offline`, `command_failed`; tự đóng khi thiết bị online lại |

DDL PostgreSQL đầy đủ: [`schema_postgres.sql`](schema_postgres.sql) (sinh từ Alembic migration).
