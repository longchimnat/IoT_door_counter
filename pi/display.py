"""LED, 16x2 I2C LCD hoặc màn hình HDMI, có console dự phòng khi phát triển.

Chọn thiết bị hiển thị bằng biến môi trường DISPLAY_MODE:
  lcd    (mặc định)  LCD 16x2 I2C
  screen             màn hình HDMI: cửa sổ toàn màn hình hiện số lượt + trạng thái phòng
Khi dùng screen, SCREEN_FULLSCREEN=0 để mở cửa sổ thường thay vì toàn màn hình.
"""
from __future__ import annotations

import logging
import os
import threading

from . import config as cfg

log = logging.getLogger(__name__)

FONT_FAMILY = "DejaVu Sans"  # nếu thiếu font, tkinter tự chọn font thay thế
TEXT_OCCUPIED = "CÓ NGƯỜI"
TEXT_EMPTY = "PHÒNG TRỐNG"


def status_text(occupied: bool) -> str:
    return TEXT_OCCUPIED if occupied else TEXT_EMPTY


class Leds:
    def __init__(self, mock: bool = False):
        self.mock = mock
        self._red = self._green = None
        self._occupied: bool | None = None
        if not mock:
            from gpiozero import LED

            self._red = LED(cfg.LED_RED_PIN)
            try:
                self._green = LED(cfg.LED_GREEN_PIN)
            except Exception:
                self._red.close()
                self._red = None
                raise

    def show_room(self, occupied: bool) -> None:
        occupied = bool(occupied)
        if self._occupied == occupied:
            return
        self._occupied = occupied
        if not self.mock:
            self._red.value = occupied
            self._green.value = not occupied

    set_occupied = show_room

    @property
    def state(self):
        return self._occupied

    def all_off(self) -> None:
        if not self.mock:
            if self._red is not None:
                self._red.off()
            if self._green is not None:
                self._green.off()

    def close(self) -> None:
        self.all_off()
        for led in (self._red, self._green):
            if led is not None:
                led.close()
        self._red = self._green = None
        self._occupied = None


class Lcd:
    """Thin wrapper around RPLCD, kept separate from the display fallback."""

    def __init__(self, lcd=None, mock: bool = False):
        self.mock = mock
        if mock:
            self._lcd = None
        else:
            if lcd is None:
                from RPLCD.i2c import CharLCD

                lcd = CharLCD(
                    "PCF8574",
                    address=cfg.LCD_I2C_ADDRESS,
                    port=cfg.LCD_I2C_PORT,
                    cols=cfg.LCD_COLUMNS,
                    rows=cfg.LCD_ROWS,
                    auto_linebreaks=False,
                )
            self._lcd = lcd

    def show(self, count: int, occupied: bool) -> None:
        if self._lcd is None:
            return
        first = f"Luot: {int(count)}"[:cfg.LCD_COLUMNS].ljust(cfg.LCD_COLUMNS)
        second = ("CO NGUOI" if occupied else "PHONG TRONG")[:cfg.LCD_COLUMNS].ljust(cfg.LCD_COLUMNS)
        self._lcd.cursor_pos = (0, 0)
        self._lcd.write_string(first)
        self._lcd.cursor_pos = (1, 0)
        self._lcd.write_string(second)

    def close(self) -> None:
        if self._lcd is not None:
            try:
                self._lcd.clear()
                self._lcd.backlight_enabled = False
            finally:
                self._lcd = None


class ScreenWindow:
    """Màn hình HDMI: cửa sổ tkinter hiện số lượt và trạng thái phòng.

    Chạy trong một luồng riêng, chỉ luồng đó chạm vào tkinter; chương trình chính chỉ
    gọi show(count, occupied) (giống Lcd.show) nên vòng đo không bị chậm.
    Nền ĐỎ = có người, nền XANH = phòng trống. Nhấn Esc để thoát chế độ toàn màn hình.
    """

    COLOR_OCCUPIED = "#c62828"
    COLOR_EMPTY = "#2e7d32"

    def __init__(self, fullscreen: bool = True, poll_ms: int = 100):
        self._fullscreen = fullscreen
        self._poll_ms = poll_ms
        self._state = (0, False)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name="screen", daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            self._stop.set()
            raise RuntimeError("Cửa sổ hiển thị không khởi động được (quá thời gian chờ)")
        if self._error is not None:
            raise self._error

    def _run(self) -> None:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.title("Đếm lượt người qua cửa")
            if self._fullscreen:
                root.attributes("-fullscreen", True)
                root.bind("<Escape>", lambda _e: root.attributes("-fullscreen", False))
            else:
                root.geometry("1024x600")
            height = max(root.winfo_screenheight() if self._fullscreen else 600, 300)

            title = tk.Label(root, text="LƯỢT QUA CỬA", fg="white")
            number = tk.Label(root, text="0", fg="white")
            status = tk.Label(root, text=status_text(False), fg="white")
            title.configure(font=(FONT_FAMILY, -int(height * 0.09)))
            number.configure(font=(FONT_FAMILY, -int(height * 0.42), "bold"))
            status.configure(font=(FONT_FAMILY, -int(height * 0.13), "bold"))
            title.pack(pady=(int(height * 0.04), 0))
            number.pack(expand=True)
            status.pack(pady=(0, int(height * 0.06)))

            shown = [None]

            def paint(state):
                count, occupied = state
                color = self.COLOR_OCCUPIED if occupied else self.COLOR_EMPTY
                root.configure(bg=color)
                for widget in (title, number, status):
                    widget.configure(bg=color)
                number.configure(text=str(count))
                status.configure(text=status_text(occupied))

            def poll():
                if self._stop.is_set():
                    root.destroy()
                    return
                with self._lock:
                    state = self._state
                if state != shown[0]:
                    shown[0] = state
                    paint(state)
                root.after(self._poll_ms, poll)

            paint(self._state)
            shown[0] = self._state
            self._ready.set()
            root.after(self._poll_ms, poll)
            root.mainloop()
            # Giải phóng đối tượng tkinter ngay trong luồng này, tránh lỗi khi thoát chương trình
            del title, number, status, root, paint, poll
        except BaseException as exc:  # noqa: BLE001 - báo lỗi về luồng chính
            if not self._ready.is_set():
                self._error = exc
                self._ready.set()
            else:
                log.warning("Cửa sổ hiển thị dừng: %s", exc)
        finally:
            import gc

            gc.collect()

    def show(self, count: int, occupied: bool) -> None:
        with self._lock:
            self._state = (int(count), bool(occupied))

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


def create_outputs(mock: bool = False):
    leds = Leds(mock=mock)
    try:
        lcd = Lcd(mock=mock)
    except Exception:
        leds.close()
        raise
    return leds, lcd


class Display:
    """Keep LCD output best-effort; if I2C is unavailable, log to console."""

    def __init__(self, fullscreen: bool = True, console_only: bool = False, log=None,
                 mode: str | None = None):
        self.fullscreen = fullscreen  # accepted for compatibility with older launch scripts
        self.mode = (mode or os.environ.get("DISPLAY_MODE", "lcd")).strip().lower()
        self.console_only = console_only
        self._log = log or (lambda message: print(message))
        self._lcd = None
        self._last = None

    @property
    def uses_window(self) -> bool:
        return self._lcd is not None and not self.console_only

    uses_lcd = uses_window

    def start(self) -> None:
        if self.console_only:
            return
        try:
            if self.mode == "screen":
                windowed = os.environ.get("SCREEN_FULLSCREEN", "1").strip() == "0"
                self._lcd = ScreenWindow(fullscreen=self.fullscreen and not windowed)
            else:
                self._lcd = Lcd()
        except Exception as exc:
            name = "màn hình HDMI" if self.mode == "screen" else "LCD I2C"
            log.warning("Không mở được %s, chuyển sang console: %s", name, exc)
            self._lcd = None
            self.console_only = True

    def update(self, count: int, occupied: bool) -> None:
        state = (int(count), bool(occupied))
        if self.console_only:
            if state != self._last:
                self._log(f"[DISPLAY] Lượt: {state[0]} | {status_text(state[1])}")
        elif self._lcd is not None:
            self._lcd.show(*state)
        self._last = state

    def close(self) -> None:
        if self._lcd is not None:
            try:
                self._lcd.close()
            finally:
                self._lcd = None
