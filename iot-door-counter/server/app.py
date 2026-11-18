"""[Người D] Backend Flask + SQLite - CHƯA LÀM, D viết trong file này.

HỢP ĐỒNG: xem docs/API.md (định dạng JSON và endpoint). Cần có:
  POST /api/events            Pi gửi lượt qua cửa / đổi trạng thái phòng
  GET  /api/status            {"count_today", "room_status", "last_update"}
  GET  /api/stats/hourly      số lượt theo 24 giờ (?date=YYYY-MM-DD)
  POST /api/reset             web bấm reset
  GET  /api/commands          Pi hỏi có lệnh (reset) không
  GET  /api/health            {"ok": true}
  GET  /                      trả về web/index.html

Cần create_app(db_path=None) trả về Flask app (để tests/test_server.py dùng).
Chạy: python -m server.app
Đổi endpoint hay JSON phải báo leader và sửa docs/API.md trước.
"""


def create_app(db_path=None):
    # TODO(D)
    raise NotImplementedError("TODO(D)")
