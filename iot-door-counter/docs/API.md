# Hợp đồng giao diện Pi ↔ Server ↔ Web

> Đây là "luật chung". Muốn đổi gì phải báo leader và sửa file này trước.
> Thời gian luôn là **ISO 8601 UTC** (ví dụ `2026-11-12T03:15:00+00:00`).

## 1. Pi gửi sự kiện lên server — `POST /api/events`

Lượt qua cửa:
```json
{"device_id": "pi1", "timestamp": "2026-11-12T03:15:00+00:00", "type": "pass", "count_today": 12}
```
Đổi trạng thái phòng:
```json
{"device_id": "pi1", "timestamp": "2026-11-12T03:20:00+00:00", "type": "room_status", "room_status": "occupied"}
```
- `type`: `"pass"` hoặc `"room_status"`.
- `room_status`: `"occupied"` (có người) hoặc `"empty"` (trống).
- Trả `201 {"ok": true}`; sai định dạng trả `400 {"error": "..."}`.

## 2. Web lấy dữ liệu

| Endpoint | Trả về |
|---|---|
| `GET /api/status` | `{"count_today": 12, "room_status": "occupied", "last_update": "<ISO>"}` |
| `GET /api/stats/hourly?date=YYYY-MM-DD` | `{"date": "...", "hours": [{"hour": 0, "count": 0}, ... 24 phần tử]}` (giờ theo múi giờ VN; bỏ `date` = hôm nay) |
| `GET /api/health` | `{"ok": true}` |

## 3. Reset từ web

- Web: `POST /api/reset` → server lưu lệnh, `count_today` tính lại từ thời điểm reset.
- Pi hỏi định kỳ: `GET /api/commands?device_id=pi1` → `{"commands": [{"id": 3, "type": "reset"}]}`
  (mỗi lệnh chỉ trả 1 lần). Pi nhận được thì gọi `counter.reset()`.
- Biểu đồ theo giờ **vẫn giữ lịch sử** sau reset (chỉ bộ đếm về 0). Nhóm có thể đổi quy ước này nếu muốn.

## 4. Ranh giới giữa các module (Pi)

| Module | Hàm công khai |
|---|---|
| `sensors.py` | `UltrasonicSensor.read_cm() -> float \| None`, `PirSensor.motion() -> bool` |
| `display.py` | `Leds.show_room(occupied)`, `Lcd.show(count, occupied)` |
| `counter.py` | `DoorCounter.update(distance_cm, now) -> bool`, `.count`, `.reset()` |
| `room_state.py` | `RoomState.update(motion, now) -> bool`, `.occupied` |
| `client.py` | `ApiClient.send_event(type, **fields)`, `ApiClient.fetch_commands()` |
