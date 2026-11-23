"""counter.py - Thuật toán đếm lượt người từ chuỗi khoảng cách HC-SR04.

Người phụ trách: C (Huệ). Hàm công khai: Counter.update(), reset(), recalibrate().

Quy tắc theo đề:
  1. Khoảng cách giảm đột ngột (xuống dưới DROP_RATIO x nền) rồi trở lại
     (từ RETURN_RATIO x nền trở lên) thì tính 1 lượt, tại thời điểm trở lại.
  2. Hai lần chắn cách nhau dưới MIN_GAP_S giây chỉ tính 1 lượt (khoảng cách
     tính từ lúc lần chắn trước kết thúc đến lúc lần chắn sau bắt đầu).

Thêm để chạy ổn ở cửa thật:
  - Khử nhiễu: cần DEBOUNCE_SAMPLES mẫu liên tiếp mới xác nhận chắn/trả lại,
    một mẫu nhiễu lẻ không làm đếm sai.
  - Hai ngưỡng (DROP < RETURN) tạo vùng đệm, tránh dao động quanh một ngưỡng.
  - Khoảng cách nền lấy từ trung vị các mẫu đầu, rồi cập nhật chậm khi nền trôi.
  - Vật đứng yên quá MAX_BLOCK_S giây (cửa đóng, thùng để lại): học lại nền, không đếm.
  - Nền xa hơn liên tục (mở cửa, vật cản đi mất): đổi nền nhanh.
  - Mẫu không hợp lệ (None, dưới MIN_VALID_CM) bị bỏ qua.

Cần để cửa trống (không ai đứng chắn) trong lúc khởi động để lấy nền đúng;
nếu lấy sai thì nền tự sửa sau khi người đó đi khỏi.
"""
import statistics
import time

from pi import config as cfg

CALIBRATING = "calibrating"
IDLE = "idle"
BLOCKED = "blocked"


class Counter:
    def __init__(self, drop_ratio=cfg.DROP_RATIO, return_ratio=cfg.RETURN_RATIO,
                 min_gap_s=cfg.MIN_GAP_S, max_block_s=cfg.MAX_BLOCK_S,
                 debounce=cfg.DEBOUNCE_SAMPLES, baseline_samples=cfg.BASELINE_SAMPLES,
                 baseline_alpha=cfg.BASELINE_ALPHA, far_ratio=cfg.FAR_RATIO,
                 rebase_samples=cfg.REBASE_SAMPLES, min_valid_cm=cfg.MIN_VALID_CM,
                 max_cm=cfg.MAX_DISTANCE_CM):
        if not 0 < drop_ratio < return_ratio <= 1.0:
            raise ValueError("cần 0 < drop_ratio < return_ratio <= 1")
        if far_ratio <= 1.0:
            raise ValueError("far_ratio phải > 1")
        if min(debounce, baseline_samples, rebase_samples) < 1:
            raise ValueError("debounce, baseline_samples, rebase_samples phải >= 1")
        if min_gap_s < 0 or max_block_s <= 0 or not 0 < baseline_alpha <= 1:
            raise ValueError("min_gap_s, max_block_s hoặc baseline_alpha không hợp lệ")
        self.drop_ratio = drop_ratio
        self.return_ratio = return_ratio
        self.min_gap_s = min_gap_s
        self.max_block_s = max_block_s
        self.debounce = debounce
        self.baseline_samples = baseline_samples
        self.baseline_alpha = baseline_alpha
        self.far_ratio = far_ratio
        self.rebase_samples = rebase_samples
        self.min_valid_cm = min_valid_cm
        self.max_cm = max_cm

        self.count = 0
        self.baseline = None
        self.state = CALIBRATING
        self.last_pass_t = None
        self._clear_runtime()

    # ------------------------------------------------------------ công khai
    def update(self, distance_cm, t=None):
        """Nạp một mẫu khoảng cách (cm). Trả về True nếu mẫu này làm tăng số lượt."""
        if t is None:
            t = time.monotonic()
        if distance_cm is None or distance_cm < self.min_valid_cm:
            return False                       # mẫu lỗi: bỏ qua
        d = min(float(distance_cm), float(self.max_cm))
        if self.state == CALIBRATING:
            return self._calibrate(d)
        if self.state == IDLE:
            return self._idle(d, t)
        return self._blocked(d, t)

    def reset(self):
        """Đưa số lượt về 0 (nút reset trên web). Giữ nguyên khoảng cách nền."""
        self.count = 0

    def recalibrate(self):
        """Học lại khoảng cách nền từ đầu (giữ nguyên số lượt)."""
        self.state = CALIBRATING
        self._clear_runtime()

    # -------------------------------------------------------------- nội bộ
    def _clear_runtime(self):
        self._cal = []
        self._low_streak = 0
        self._low_start = 0.0
        self._high_streak = 0
        self._high_start = 0.0
        self._block_start = 0.0
        self._merged = False
        self._far = []
        self._last_block_end = float("-inf")

    def _calibrate(self, d):
        self._cal.append(d)
        if len(self._cal) >= self.baseline_samples:
            self.baseline = statistics.median(self._cal)
            self._cal = []
            self.state = IDLE
            self._low_streak = 0
            self._far = []
        return False

    def _idle(self, d, t):
        base = self.baseline
        if d < base * self.drop_ratio:                       # có vẻ đang bị chắn
            if self._low_streak == 0:
                self._low_start = t
            self._low_streak += 1
            self._far = []
            if self._low_streak >= self.debounce:
                self.state = BLOCKED
                self._block_start = self._low_start
                self._merged = (self._block_start - self._last_block_end) < self.min_gap_s
                self._high_streak = 0
            return False

        self._low_streak = 0
        if d > base * self.far_ratio:                        # xa hơn nền liên tục: đổi nền
            self._far.append(d)
            if len(self._far) >= self.rebase_samples:
                self.baseline = statistics.median(self._far)
                self._far = []
        else:
            self._far = []
            if d >= base * self.return_ratio:                # gần nền: trôi chậm theo
                self.baseline = base + self.baseline_alpha * (d - base)
        return False

    def _blocked(self, d, t):
        if t - self._block_start > self.max_block_s:         # vật đứng yên quá lâu
            self.state = CALIBRATING
            self._cal = [d]
            self._high_streak = 0
            self._last_block_end = t
            return False
        if d >= self.baseline * self.return_ratio:           # đã trả lại
            if self._high_streak == 0:
                self._high_start = t
            self._high_streak += 1
            if self._high_streak >= self.debounce:
                self.state = IDLE
                self._low_streak = 0
                self._far = []
                self._last_block_end = self._high_start
                if not self._merged:
                    self.count += 1
                    self.last_pass_t = self._high_start
                    return True
            return False
        self._high_streak = 0                                # vẫn chắn hoặc vùng đệm
        return False
