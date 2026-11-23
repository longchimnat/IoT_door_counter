"""config.py - Hằng số chung của phần chạy trên Raspberry Pi.

Người phụ trách: A (Long). Không commit mật khẩu/token: đặt qua biến môi trường.
Mọi giá trị có thể ghi đè bằng biến môi trường cùng tên, ví dụ:
    API_URL=http://192.168.1.50:5000 python -m pi.main
"""
import os


def _env(name, default):
    """Đọc biến môi trường, ép về cùng kiểu với giá trị mặc định."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return type(default)(raw)
    except ValueError:
        raise ValueError(f"Biến môi trường {name}={raw!r} không hợp lệ")


# ---------------------------------------------------------------- GPIO (BCM)
TRIG_PIN = _env("TRIG_PIN", 23)            # HC-SR04 Trig  - chân vật lý 16
ECHO_PIN = _env("ECHO_PIN", 24)            # HC-SR04 Echo  - chân vật lý 18 (QUA cầu phân áp)
PIR_PIN = _env("PIR_PIN", 17)              # PIR OUT       - chân vật lý 11
LED_GREEN_PIN = _env("LED_GREEN_PIN", 27)  # LED xanh      - chân vật lý 13
LED_RED_PIN = _env("LED_RED_PIN", 22)      # LED đỏ        - chân vật lý 15

# ----------------------------------------------------------- Đo khoảng cách
MAX_DISTANCE_CM = _env("MAX_DISTANCE_CM", 200)  # xa hơn = "không có vật cản"
MIN_VALID_CM = _env("MIN_VALID_CM", 2.0)        # HC-SR04 không đo được dưới ~2 cm
SAMPLE_INTERVAL_S = _env("SAMPLE_INTERVAL_S", 0.05)  # 20 lần đo mỗi giây

# ------------------------------------------------------------ Thuật toán đếm
DROP_RATIO = _env("DROP_RATIO", 0.70)      # khoảng cách < nền x tỉ lệ này = bị chắn
RETURN_RATIO = _env("RETURN_RATIO", 0.85)  # khoảng cách >= nền x tỉ lệ này = đã trả lại
MIN_GAP_S = _env("MIN_GAP_S", 1.0)         # hai lần chắn cách nhau < 1 giây chỉ tính 1
DEBOUNCE_SAMPLES = _env("DEBOUNCE_SAMPLES", 2)   # số mẫu liên tiếp để xác nhận chắn/trả lại
MAX_BLOCK_S = _env("MAX_BLOCK_S", 8.0)     # chắn quá lâu = vật đứng yên, học lại nền
BASELINE_SAMPLES = _env("BASELINE_SAMPLES", 15)  # số mẫu để lấy khoảng cách nền lúc khởi động
BASELINE_ALPHA = _env("BASELINE_ALPHA", 0.02)    # tốc độ cập nhật nền chậm (0..1)
FAR_RATIO = _env("FAR_RATIO", 1.20)        # xa hơn nền x tỉ lệ này liên tục = nền đã đổi
REBASE_SAMPLES = _env("REBASE_SAMPLES", 10)

# --------------------------------------------------------- Trạng thái phòng
PIR_TIMEOUT_S = _env("PIR_TIMEOUT_S", 300.0)  # 5 phút không chuyển động = phòng trống
PIR_WARMUP_S = _env("PIR_WARMUP_S", 30.0)     # PIR báo nhiễu 30-60 giây đầu, bỏ qua

# ----------------------------------------------------------------- Mạng/API
API_URL = _env("API_URL", "http://127.0.0.1:5000")
API_TOKEN = _env("API_TOKEN", "")             # để trống nếu server không cần
DEVICE_ID = _env("DEVICE_ID", "pi-door-1")
API_EVENTS_PATH = "/api/events"               # POST: mỗi lượt đi qua
API_STATE_PATH = "/api/state"                 # POST: trạng thái phòng (có người/trống)
API_STATUS_PATH = "/api/status"               # GET : lệnh từ web (reset_seq)
HTTP_TIMEOUT_S = _env("HTTP_TIMEOUT_S", 3.0)
SEND_RETRY_INTERVAL_S = _env("SEND_RETRY_INTERVAL_S", 5.0)  # chờ giữa các lần gửi lại
COMMAND_POLL_INTERVAL_S = _env("COMMAND_POLL_INTERVAL_S", 2.0)
STATE_HEARTBEAT_S = _env("STATE_HEARTBEAT_S", 30.0)         # gửi lại trạng thái định kỳ
QUEUE_FILE = _env("QUEUE_FILE", "data/pending_events.jsonl")  # hàng đợi gửi bù khi mất mạng
MAX_QUEUE = _env("MAX_QUEUE", 50000)
