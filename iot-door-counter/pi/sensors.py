"""[Người B] Driver cảm biến - CHƯA LÀM, B viết trong file này.

HỢP ĐỒNG (không đổi chữ ký khi chưa báo leader; xem docs/API.md mục 4):
  UltrasonicSensor.read_cm() -> float | None    # khoảng cách cm, None nếu đo lỗi
  PirSensor.motion()         -> bool            # True nếu đang thấy chuyển động
  create_sensors(mock=False) -> (ultrasonic, pir)
      mock=True  : trả về bản giả lập (để cả nhóm chạy thử không cần phần cứng)
      mock=False : trả về cảm biến thật

Gợi ý: dùng gpiozero (DistanceSensor, MotionSensor); chân GPIO lấy từ pi/config.py.
Nhớ cầu phân áp cho chân Echo (5V -> 3.3V).
"""
from . import config  # noqa: F401


class UltrasonicSensor:
    # TODO(B)
    def read_cm(self):
        raise NotImplementedError("TODO(B)")


class PirSensor:
    # TODO(B)
    def motion(self):
        raise NotImplementedError("TODO(B)")


def create_sensors(mock=False):
    # TODO(B)
    raise NotImplementedError("TODO(B)")
