"""[Người B] LED + LCD I2C - CHƯA LÀM, B viết trong file này.

HỢP ĐỒNG (không đổi chữ ký khi chưa báo leader; xem docs/API.md mục 4):
  Leds.show_room(occupied: bool)       # đỏ = có người, xanh = phòng trống
  Lcd.show(count: int, occupied: bool) # dòng 1: số lượt; dòng 2: trạng thái phòng
  create_outputs(mock=False) -> (leds, lcd)
      mock=True  : bản giả lập in ra console (chạy thử không cần phần cứng)
      mock=False : LED và LCD thật

Gợi ý: gpiozero.LED cho LED, RPLCD.i2c.CharLCD cho LCD. Chân và địa chỉ LCD lấy từ pi/config.py.
"""
from . import config  # noqa: F401


class Leds:
    # TODO(B)
    def show_room(self, occupied):
        raise NotImplementedError("TODO(B)")


class Lcd:
    # TODO(B)
    def show(self, count, occupied):
        raise NotImplementedError("TODO(B)")


def create_outputs(mock=False):
    # TODO(B)
    raise NotImplementedError("TODO(B)")
