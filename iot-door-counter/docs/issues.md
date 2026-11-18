# Danh sách Issue ban đầu (dán vào GitHub Issues)

**[A - Leader]**
- Tạo repo, mời thành viên, tạo Issue, họp kickoff
- Cài Raspberry Pi OS, bật SSH và I2C
- Hỏi giảng viên: deadline, tiêu chí chấm, hình thức demo
- Sau khi B, C xong: chạy `python -m pi.main --mock`, rồi với phần cứng thật
- Cho Pi tự chạy khi bật nguồn (systemd)
- Họp tuần, review Pull Request, theo dõi tiến độ

**[B] Phần cứng** (viết `pi/sensors.py`, `pi/display.py`)
- Kiểm kê bộ kit, đấu mạch HC-SR04 có cầu phân áp, vẽ sơ đồ đấu dây (docs/)
- Viết `UltrasonicSensor`, `PirSensor`, `create_sensors` (có bản mock)
- Viết `Leds`, `Lcd`, `create_outputs` (có bản mock)
- Ghi dữ liệu đo thô khi có người đi qua, gửi cho C

**[C] Thuật toán** (viết `pi/counter.py`, `tests/test_counter.py`)
- Viết `DoorCounter`: đo nền, giảm đột ngột rồi trở lại = 1 lượt
- Chống đếm trùng dưới 1 giây
- Viết test bằng dữ liệu giả
- Chỉnh ngưỡng bằng số liệu thật, thử người đi nhanh/chậm/sát nhau

**[D] Backend** (viết `server/app.py`, `tests/test_server.py`)
- Viết API theo `docs/API.md` (Flask + SQLite)
- Viết test API
- Hướng dẫn chạy server trên laptop/Pi, mở cổng, cố định IP

**[E] Frontend + tài liệu** (viết `web/index.html`)
- Biểu đồ lượt theo giờ + nút reset
- Báo cáo, slide, video demo
