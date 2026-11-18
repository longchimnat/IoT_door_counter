"""[Người C] Thuật toán đếm lượt qua cửa - CHƯA LÀM, C viết trong file này.

HỢP ĐỒNG (không đổi chữ ký khi chưa báo leader; xem docs/API.md mục 4):
  DoorCounter.update(distance_cm, now) -> bool   # True nếu vừa đếm thêm 1 lượt
  DoorCounter.count                               # số lượt hiện tại
  DoorCounter.reset()                             # đưa count về 0

Yêu cầu theo đề:
  - Khoảng cách giảm đột ngột rồi trở lại như cũ = 1 lượt.
  - Hai lần bị chắn cách nhau dưới 1 giây chỉ tính 1 (DEBOUNCE_SECONDS).
Hằng số (DROP_RATIO, DEBOUNCE_SECONDS, BASELINE_SAMPLES) lấy từ pi/config.py.
Không phụ thuộc phần cứng: test bằng dữ liệu giả trong tests/test_counter.py.
"""
from . import config


class DoorCounter:
    def __init__(self,
                 baseline_samples=config.BASELINE_SAMPLES,
                 drop_ratio=config.DROP_RATIO,
                 debounce_seconds=config.DEBOUNCE_SECONDS):
        self.count = 0
        # TODO(C)

    def update(self, distance_cm, now):
        raise NotImplementedError("TODO(C)")

    def reset(self):
        raise NotImplementedError("TODO(C)")
