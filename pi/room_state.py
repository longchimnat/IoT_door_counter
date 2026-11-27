"""room_state.py - Trạng thái phòng từ PIR.

Người phụ trách: A (Long).

Quy tắc theo đề:
  - PIR thấy chuyển động -> phòng CÓ NGƯỜI (LED đỏ), đặt lại bộ đếm 5 phút.
  - PIR không thấy chuyển động liên tục TIMEOUT giây (mặc định 300 = 5 phút)
    -> phòng TRỐNG (LED xanh).
Lúc khởi động coi phòng là trống cho đến khi PIR thấy chuyển động đầu tiên.
"""
import time

from pi import config as cfg


class RoomState:
    def __init__(self, timeout_s=cfg.PIR_TIMEOUT_S, initial_occupied=False):
        if timeout_s <= 0:
            raise ValueError("timeout_s phải > 0")
        self.timeout_s = float(timeout_s)
        self.occupied = bool(initial_occupied)
        self._last_motion = None

    def update(self, motion, now=None):
        """Nạp một lần đọc PIR. Trả về True nếu trạng thái phòng vừa đổi."""
        if now is None:
            now = time.monotonic()
        before = self.occupied
        if motion:
            self._last_motion = now
            self.occupied = True
        elif self.occupied:
            if self._last_motion is None:      # khởi động ở trạng thái "có người"
                self._last_motion = now
            if now - self._last_motion >= self.timeout_s:
                self.occupied = False
        return self.occupied != before

    @property
    def led(self):
        """Màu LED cần sáng: 'red' (có người) hoặc 'green' (trống)."""
        return "red" if self.occupied else "green"

    def seconds_until_empty(self, now=None):
        """Số giây còn lại đến khi phòng chuyển sang trống (None nếu đang trống)."""
        if not self.occupied or self._last_motion is None:
            return None
        if now is None:
            now = time.monotonic()
        return max(0.0, self.timeout_s - (now - self._last_motion))
