"""[Leader / Người A] Trạng thái phòng từ PIR.
PIR không thấy chuyển động liên tục EMPTY_TIMEOUT_SECONDS (5 phút) => phòng trống.

HỢP ĐỒNG:
  RoomState.update(motion: bool, now: float) -> bool  (True nếu trạng thái vừa đổi)
  RoomState.occupied -> bool
"""
from . import config


class RoomState:
    def __init__(self, timeout_seconds=config.EMPTY_TIMEOUT_SECONDS):
        self.timeout = timeout_seconds
        self.occupied = False
        self._last_motion = None

    def update(self, motion, now):
        if motion:
            self._last_motion = now
        new = (self._last_motion is not None
               and now - self._last_motion < self.timeout)
        changed = new != self.occupied
        self.occupied = new
        return changed
