# IoT Door Counter (Capstone SIC 2026 – Đề tài 2)

Đếm lượt người qua cửa bằng Raspberry Pi + HC-SR04 + PIR + LED + LCD I2C, gửi dữ liệu lên web server.

```
HC-SR04 ─┐                               ┌─> LCD / LED
PIR ─────┴─> Pi (pi/main.py) ──HTTP/JSON─┴─> Server (server/app.py) ──> Web (web/index.html)
```

## Trạng thái

| Phần | Người | File | Trạng thái |
|---|---|---|---|
| Ghép nối, trạng thái phòng, cấu hình | **A (leader)** | `pi/main.py`, `pi/room_state.py`, `pi/client.py`, `pi/config.py`, `docs/API.md` | Đã có code |
| Cảm biến, LED, LCD | **B** | `pi/sensors.py`, `pi/display.py` | Rỗng, B làm |
| Thuật toán đếm | **C** | `pi/counter.py`, `tests/test_counter.py` | Rỗng, C làm |
| Backend | **D** | `server/app.py`, `tests/test_server.py` | Rỗng, D làm |
| Web, báo cáo | **E** | `web/index.html` | Rỗng, E làm |

Mỗi file rỗng có sẵn **hợp đồng** (tên hàm, tham số, giá trị trả về) ở đầu file. Làm đúng hợp đồng thì phần của A ghép vào được ngay.
**Luật chung:** không đổi hàm công khai hay JSON (xem `docs/API.md`) khi chưa báo leader. Hằng số để hết trong `pi/config.py`.

## Cách làm việc với Git

1. Clone repo, tạo branch riêng (`feature/counter`, `feature/server`...). Không push thẳng vào `main`.
2. Chỉ sửa file của mình (bảng trên) để ít xung đột; làm xong mở Pull Request, leader review rồi merge.
3. `git pull` thường xuyên để lấy bản mới nhất.
4. Không commit mật khẩu/token. Danh sách việc ban đầu: `docs/issues.md`.

## Chạy thử

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install flask requests pytest
pytest -q                          # test phần của A chạy được ngay
```
Khi B (có bản mock), C và D đã xong phần của mình:
```bash
python -m server.app               # cửa sổ 1: mở http://localhost:5000
python -m pi.main --mock           # cửa sổ 2: Pi giả lập
```
Trên Raspberry Pi thật: bật I2C bằng `sudo raspi-config`, `pip install -r pi/requirements.txt`,
rồi `API_URL=http://<IP-server>:5000 python -m pi.main`.
**Echo của HC-SR04 phải qua cầu phân áp trước khi vào GPIO.**
