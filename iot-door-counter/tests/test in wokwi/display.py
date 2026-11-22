"""display.py - Hiển thị số lượt và trạng thái phòng trên LCD 1602 I2C (Wokwi / Pico).

Người phụ trách: B (Trang). Thay cho bản Tkinter 7" ở pi/display.py: MicroPython
không có Tkinter, và roadmap vốn dùng LCD I2C. API giữ nguyên:
    disp = Display(); disp.start(); disp.update(count, occupied); disp.close()
Không tìm thấy LCD trên I2C thì tự chuyển sang in ra console.

LCD 1602 không có chữ có dấu nên trên LCD dùng "CO NGUOI" / "PHONG TRONG";
console vẫn in tiếng Việt có dấu.
"""
import time

try:
    from machine import I2C, Pin
except ImportError:
    I2C = Pin = None

I2C_SDA = 4
I2C_SCL = 5
LCD_ADDR = 0x27

COLOR_OCCUPIED = "red"
COLOR_EMPTY = "green"
TEXT_OCCUPIED = "CÓ NGƯỜI"
TEXT_EMPTY = "PHÒNG TRỐNG"
LCD_OCCUPIED = "CO NGUOI"
LCD_EMPTY = "PHONG TRONG"


def status_text(occupied):
    return TEXT_OCCUPIED if occupied else TEXT_EMPTY


def lcd_text(occupied):
    return LCD_OCCUPIED if occupied else LCD_EMPTY


class Lcd:
    """Driver LCD HD44780 qua bộ mở rộng PCF8574 (4-bit)."""
    _RS, _E, _BL = 0x01, 0x04, 0x08

    def __init__(self, i2c, addr=LCD_ADDR, cols=16, rows=2):
        self.i2c, self.addr, self.cols, self.rows = i2c, addr, cols, rows
        time.sleep(0.05)
        for wait in (0.005, 0.005, 0.001):
            self._nibble(0x03, 0)
            time.sleep(wait)
        self._nibble(0x02, 0)             # chuyển sang chế độ 4-bit
        self._send(0x28, 0)               # 2 dòng, font 5x8
        self._send(0x0C, 0)               # bật hiển thị, tắt con trỏ
        self._send(0x06, 0)               # con trỏ chạy sang phải
        self.clear()

    def _nibble(self, n, rs):
        d = (n << 4) | self._BL | rs
        self.i2c.writeto(self.addr, bytes([d | self._E]))
        time.sleep(0.001)
        self.i2c.writeto(self.addr, bytes([d]))
        time.sleep(0.001)

    def _send(self, byte, rs):
        self._nibble(byte >> 4, rs)
        self._nibble(byte & 0x0F, rs)

    def clear(self):
        self._send(0x01, 0)
        time.sleep(0.003)

    def put_line(self, row, text):
        self._send(0x80 | (0x40 if row else 0x00), 0)
        text = (text + " " * self.cols)[:self.cols]
        for ch in text:
            self._send(ord(ch) & 0x7F, self._RS)

    def backlight(self, on):
        self._BL = 0x08 if on else 0x00
        self.i2c.writeto(self.addr, bytes([self._BL]))


class Display:
    def __init__(self, fullscreen=True, console_only=False, i2c=None, addr=LCD_ADDR, log=print):
        self.fullscreen = fullscreen          # giữ cho tương thích, LCD không dùng
        self.console_only = console_only
        self.shown = None                     # (count, chữ LCD) đang hiện
        self._count = 0
        self._occupied = False
        self._i2c = i2c
        self._addr = addr
        self._lcd = None
        self._console = console_only
        self._last_printed = None
        self._log = log

    @property
    def uses_window(self):
        return self._lcd is not None and not self._console

    uses_lcd = uses_window

    def start(self):
        if self.console_only:
            return
        try:
            i2c = self._i2c or I2C(0, sda=Pin(I2C_SDA), scl=Pin(I2C_SCL), freq=400000)
            found = i2c.scan()
            self._log("[DISPLAY] I2C quét thấy: %s" % [hex(a) for a in found])
            if not found:
                raise OSError("không thấy thiết bị I2C: kiểm tra SDA=GP4, SCL=GP5, VCC, GND của LCD")
            addr = self._addr if self._addr in found else found[0]
            self._lcd = Lcd(i2c, addr)
        except Exception as exc:
            self._log("[DISPLAY] Không mở được LCD (%s); chuyển sang console." % exc)
            self._console = True
            self._lcd = None

    def update(self, count, occupied):
        self._count = int(count)
        self._occupied = bool(occupied)
        if self._console:
            state = (self._count, self._occupied)
            if state != self._last_printed:
                self._last_printed = state
                self._log("[DISPLAY] Lượt: %d | %s" % (self._count, status_text(self._occupied)))
            return
        if self._lcd is None:
            return
        text = lcd_text(self._occupied)
        if self.shown != (self._count, text):
            self._lcd.put_line(0, "Luot: %d" % self._count)
            self._lcd.put_line(1, text)
            self.shown = (self._count, text)

    def close(self):
        if self._lcd is not None:
            try:
                self._lcd.clear()
                self._lcd.backlight(False)
            except Exception:
                pass
        self._lcd = None
