# IoT Door Counter

Hệ thống đếm người qua cửa bằng HC-SR04, PIR, LED đỏ/xanh và LCD I2C. Raspberry Pi đọc cảm biến, lọc lượt đi qua, hiển thị tại chỗ và gửi dữ liệu lên backend FastAPI. Dashboard hiển thị số lượt, trạng thái phòng và biểu đồ theo giờ.

## Cấu trúc dự án

```text
pi/                 Chương trình và driver Raspberry Pi
server/             API FastAPI, xác thực, nghiệp vụ và MQTT tùy chọn
web/                Dashboard
migrations/         Migration Alembic
scripts/            Giả lập thiết bị và tạo dữ liệu mẫu
tests/              Kiểm thử backend, bộ đếm và client Pi
docs/               API, sơ đồ đấu dây và ghi chú vận hành
deploy/             Cấu hình chạy dịch vụ systemd
```

Các phần Pi, backend và web dùng chung API trong [docs/API.md](docs/API.md). Không đặt tệp `.env`, dữ liệu SQLite hoặc virtualenv trong mã nguồn.

## Chạy backend trên Windows

Yêu cầu Python 3.10 trở lên.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m server --reload
```

Mở <http://localhost:8000> để vào dashboard và <http://localhost:8000/docs> để xem API. `.env.example` chứa cấu hình demo; hãy đổi mật khẩu, JWT secret và API key trước khi đưa server ra mạng dùng thật. Có thể dùng `run_dev.bat` để tạo môi trường và khởi động bản phát triển.

## Chạy backend trên Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python -m server --reload
```

## Chạy Pi

Đấu nối theo [docs/HARDWARE.md](docs/HARDWARE.md). Trên Raspberry Pi OS, cài hỗ trợ GPIO của hệ điều hành rồi cài thư viện thiết bị:

```bash
sudo apt update
sudo apt install python3-gpiozero python3-lgpio python3-venv
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -r pi/requirements.txt
```

Đặt `API_URL` thành địa chỉ máy đang chạy backend và `API_KEY` bằng API key của thiết bị trong cấu hình server. Ví dụ trong terminal Pi:

```bash
export API_URL="http://192.168.1.10:8000"
export API_KEY="<API key của door-01>"
export DEVICE_ID="door-01"
python -m pi.main
```

Mở cổng 8000 trên máy chạy backend nếu Pi kết nối qua mạng LAN. Chế độ mock để kiểm tra luồng chương trình mà không cần cảm biến:

```bash
python -m pi.main --mock --no-server --seconds 5 --console
```

## Kiểm thử

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

Các kiểm thử backend dùng SQLite tạm. Muốn thử trên PostgreSQL, đặt `TEST_DATABASE_URL` theo hướng dẫn trong `tests/conftest.py`.

## Tính năng

- Hiệu chuẩn khoảng cách nền, khử nhiễu và chống đếm lặp trong 1 giây.
- Lưu lượt chưa gửi xuống tệp hàng đợi để gửi bù sau khi mạng trở lại.
- Đồng bộ số đếm chuẩn từ server và nhận lệnh reset có xác nhận ACK.
- PIR giữ trạng thái phòng có người đến khi hết thời gian chờ; LED đỏ báo có người và LED xanh báo phòng trống.
- Dashboard cập nhật trạng thái và biểu đồ, hỗ trợ xuất CSV và điều khiển reset.
