"""sensors.py - Driver HC-SR04, PIR, LED đỏ/xanh cho Raspberry Pi Pico (MicroPython / Wokwi).

Người phụ trách: B (Trang). Bản chuyển từ pi/sensors.py (gpiozero) sang MicroPython.
API giữ nguyên: Ultrasonic.read_cm / read_median, Pir.motion / wait_ready,
Leds.set_occupied, Hardware(mock=None|True|False) dùng được với `with`.

Sơ đồ chân (khớp diagram.json):
    HC-SR04  TRIG = GP14, ECHO = GP15
    PIR      OUT  = GP16
    LED đỏ   GP17 (có người)      LED xanh GP18 (phòng trống)
    LCD I2C  SDA = GP4, SCL = GP5 (xem display.py)
"""
import time

try:
    from machine import Pin, time_pulse_us
except ImportError:          # chạy thử trên máy tính không có machine
    Pin = None

TRIG_PIN = 14
ECHO_PIN = 15
PIR_PIN = 16
LED_RED_PIN = 17
LED_GREEN_PIN = 18
MAX_CM = 400
_CM_PER_US = 0.0343 / 2      # đi + về => chia 2


def now():
    """Giây (float). MicroPython không có time.time() chính xác nên dùng ticks_ms."""
    try:
        return time.ticks_ms() / 1000
    except AttributeError:
        return time.time()


def _rand_cm(state=[12345]):
    """Số giả ngẫu nhiên 0..MAX_CM (không cần module random)."""
    state[0] = (state[0] * 1103515245 + 12345) & 0x7FFFFFFF
    return state[0] % (MAX_CM + 1)


class Ultrasonic:
    def __init__(self, mock=False, mock_source=None, trig=TRIG_PIN, echo=ECHO_PIN):
        self.mock = mock
        self._src = list(mock_source) if mock_source is not None else None
        self._last = None
        if not mock:
            self._trig = Pin(trig, Pin.OUT)
            self._echo = Pin(echo, Pin.IN)
            self._trig.value(0)

    def read_cm(self):
        if self.mock:
            if self._src is None:
                v = _rand_cm()
            elif self._src:
                v = self._last = self._src.pop(0)
            else:
                v = self._last if self._last is not None else MAX_CM
            return min(max(v, 0), MAX_CM)
        self._trig.value(0)
        time.sleep(0.000002)
        self._trig.value(1)
        time.sleep(0.00001)
        self._trig.value(0)
        t = time_pulse_us(self._echo, 1, 30000)   # <0: quá thời gian => không vật cản
        if t < 0:
            return MAX_CM
        return min(max(t * _CM_PER_US, 0), MAX_CM)

    def read_median(self, n=5, sleep=time.sleep, interval=0.03):
        vals = []
        for _ in range(n):
            vals.append(self.read_cm())
            sleep(interval)
        vals.sort()
        return vals[len(vals) // 2]

    def close(self):
        pass


class Pir:
    def __init__(self, mock=False, mock_source=None, pin=PIR_PIN):
        self.mock = mock
        self._src = list(mock_source) if mock_source is not None else None
        self._last = False
        if not mock:
            self._pin = Pin(pin, Pin.IN, Pin.PULL_DOWN)

    def motion(self):
        if self.mock:
            if self._src:
                self._last = bool(self._src.pop(0))
            return self._last
        return bool(self._pin.value())

    def wait_ready(self, seconds=30, on_tick=None):
        """PIR thật cần 30-60 s khởi động. Mock không chờ."""
        if self.mock:
            return
        for r in range(int(seconds), 0, -1):
            if on_tick:
                on_tick(r)
            time.sleep(1)

    def close(self):
        pass


class Leds:
    def __init__(self, mock=False, log=print, red=LED_RED_PIN, green=LED_GREEN_PIN):
        self.mock = mock
        self.state = None            # True = có người (đỏ), False = trống (xanh)
        self._log = log
        if not mock:
            self._red = Pin(red, Pin.OUT)
            self._green = Pin(green, Pin.OUT)

    def set_occupied(self, occupied):
        occupied = bool(occupied)
        if occupied == self.state:
            return
        self.state = occupied
        if not self.mock:
            self._red.value(1 if occupied else 0)
            self._green.value(0 if occupied else 1)
        self._log("[LED] " + ("ĐỎ (có người)" if occupied else "XANH (trống)"))

    def close(self):
        if not self.mock and self.state is not None:
            self._red.value(0)
            self._green.value(0)
        self.state = None


class Hardware:
    """Gói 3 thiết bị. mock=None: thử phần cứng thật, lỗi thì tự chuyển mock."""

    def __init__(self, mock=None, ultrasonic_source=None, pir_source=None, log=print):
        self.ultrasonic = self.pir = self.leds = None
        if mock is None:                 # tự động: thử mạch thật, lỗi thì dùng mock
            try:
                self._build(False, ultrasonic_source, pir_source, log)
                mock = False
            except Exception as exc:
                log("[HW] Không dùng được GPIO (%s); chuyển sang mock." % exc)
                mock = True
                self._build(True, ultrasonic_source, pir_source, log)
        else:                            # chỉ định rõ True (mock) hoặc False (mạch thật)
            self._build(bool(mock), ultrasonic_source, pir_source, log)
        self.mock = bool(mock)

    def _build(self, mock, us_src, pir_src, log):
        self.ultrasonic = Ultrasonic(mock=mock, mock_source=us_src)
        self.pir = Pir(mock=mock, mock_source=pir_src)
        self.leds = Leds(mock=mock, log=log)

    def close(self):
        for dev in (self.ultrasonic, self.pir, self.leds):
            if dev is not None:
                dev.close()
        self.ultrasonic = self.pir = self.leds = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
