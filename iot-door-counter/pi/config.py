"""Cấu hình chung cho phần chạy trên Raspberry Pi.
Mọi hằng số (chân GPIO, ngưỡng, thời gian) để ở ĐÂY, không hard-code trong module.
Muốn đổi khi chạy thử: đặt biến môi trường, ví dụ  EMPTY_TIMEOUT_SECONDS=10
"""
import os

# --- Kết nối server ---
API_URL = os.getenv("API_URL", "http://127.0.0.1:5000")
DEVICE_ID = os.getenv("DEVICE_ID", "pi1")

# --- Chân GPIO (đánh số BCM) ---  [B chỉnh cho khớp mạch thật]
PIN_TRIG = 23
PIN_ECHO = 24          # NHỚ: Echo ra 5V -> phải qua cầu phân áp trước khi vào GPIO
PIN_PIR = 4
PIN_LED_RED = 17
PIN_LED_GREEN = 27

# --- LCD I2C ---
LCD_I2C_ADDR = 0x27    # kiểm tra bằng: i2cdetect -y 1
LCD_COLS = 16
LCD_ROWS = 2

# --- Vòng lặp chính ---
SAMPLE_INTERVAL = 0.1          # giây giữa 2 lần đo
COMMAND_POLL_INTERVAL = 2.0    # giây giữa 2 lần hỏi server có lệnh (reset) không

# --- Thuật toán đếm [C chỉnh] ---
BASELINE_SAMPLES = 20          # số mẫu đầu để đo "khoảng cách nền" (lúc cửa trống)
DROP_RATIO = 0.30              # khoảng cách giảm quá 30% so với nền => coi là có vật chắn
DEBOUNCE_SECONDS = 1.0         # 2 lần đếm cách nhau < 1s chỉ tính 1
MAX_DISTANCE_CM = 400

# --- Trạng thái phòng [A chỉnh] ---
EMPTY_TIMEOUT_SECONDS = int(os.getenv("EMPTY_TIMEOUT_SECONDS", 300))  # 5 phút
