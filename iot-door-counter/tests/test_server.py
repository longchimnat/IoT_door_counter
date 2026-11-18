"""[Người D] Test API - CHƯA LÀM.

Gợi ý các test cần có (dùng create_app(db_path_tạm).test_client()):
  - POST /api/events rồi GET /api/status, /api/stats/hourly
  - Luồng reset: POST /api/reset -> GET /api/commands (chỉ trả 1 lần)
  - Gửi dữ liệu sai thì trả 400
Chạy:  pytest -q
"""
