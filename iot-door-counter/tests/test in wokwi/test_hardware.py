"""test_hardware.py - Bản test tự động cho MicroPython/Wokwi (không cần pytest).

Chạy trên Wokwi: đặt MODE = "selftest" trong main.py. Chạy trên máy tính:
    python3 test_hardware.py     (cần module machine giả, xem HUONG_DAN.md)

Port từ tests/test_hardware.py: giữ các test mock, hiển thị, chuỗi demo (đồng hồ giả)
và ghi dữ liệu. Các test "GPIO ảo MockFactory" của gpiozero bỏ đi vì chính Wokwi
đã mô phỏng chân GPIO thật - kiểm bằng mạch ở chế độ demo/distance/pir.
"""
import sensors
from sensors import Hardware, Leds, Pir, Ultrasonic
import display as dsp
from display import Display, Lcd
import hardware_test as ht


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def clock(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


class StubDisplay:
    def __init__(self):
        self.calls = []

    def update(self, count, occupied):
        self.calls.append((count, occupied))


class FakeI2C:
    """I2C giả: ghi lại byte gửi đi, giải mã thành chữ hiện trên LCD."""
    def __init__(self, devices=(0x27,)):
        self.devices = list(devices)
        self.writes = []

    def scan(self):
        return self.devices

    def writeto(self, addr, data):
        self.writes.append(data[0])

    def decoded(self):
        """Trả về list (rs, byte) từ các nibble đã chốt bằng cạnh xuống của chân E."""
        nibs = []
        for prev, cur in zip(self.writes, self.writes[1:]):
            if prev & 0x04 and not cur & 0x04 and (prev & ~0x04) == cur:
                nibs.append((cur & 1, cur >> 4))
        return [(nibs[i][0], (nibs[i][1] << 4) | nibs[i + 1][1])
                for i in range(0, len(nibs) - 1, 2)]


def chay_demo(us_vals, pir_vals, seconds, timeout=300.0):
    fc = FakeClock()
    disp = StubDisplay()
    with Hardware(mock=True, ultrasonic_source=us_vals, pir_source=pir_vals,
                  log=lambda *a: None) as hw:
        res = ht.run_demo(hw, disp, seconds=seconds, timeout=timeout,
                          clock=fc.clock, sleep=fc.sleep, log=lambda *a: None)
        leds_state = hw.leds.state
    return res, disp, leds_state


# ------------------------------------------------------------------ 1. mock
def t_ultrasonic_mock_trong_khoang():
    us = Ultrasonic(mock=True)
    assert all(0 <= us.read_cm() <= sensors.MAX_CM for _ in range(200))


def t_ultrasonic_mock_kich_ban_va_kep_gia_tri():
    us = Ultrasonic(mock=True, mock_source=[150, 60, -5, 999])
    assert [us.read_cm() for _ in range(4)] == [150, 60, 0, sensors.MAX_CM]
    assert us.read_cm() == sensors.MAX_CM          # hết danh sách: giữ giá trị cuối


def t_ultrasonic_median_loc_nhieu():
    us = Ultrasonic(mock=True, mock_source=[100, 5, 100])
    assert us.read_median(3, sleep=lambda s: None) == 100


def t_pir_mock_kich_ban():
    pir = Pir(mock=True, mock_source=[True, False])
    assert pir.motion() is True
    assert pir.motion() is False


def t_pir_wait_ready_mock_khong_cho():
    t0 = sensors.now()
    Pir(mock=True).wait_ready(30)
    assert sensors.now() - t0 < 0.5


def t_leds_mock_trang_thai_va_in_khi_doi():
    out = []
    leds = Leds(mock=True, log=out.append)
    leds.set_occupied(True)
    leds.set_occupied(True)       # trùng, không in lại
    leds.set_occupied(False)
    assert len(out) == 2 and all(o.startswith("[LED]") for o in out)
    assert leds.state is False
    leds.close()
    assert leds.state is None


def t_hardware_mock_context_manager():
    with Hardware(mock=True, ultrasonic_source=[120], pir_source=[True]) as hw:
        assert hw.mock is True
        assert hw.ultrasonic.read_cm() == 120
        assert hw.pir.motion() is True
    assert hw.ultrasonic is None


def t_hardware_tu_chuyen_mock_khi_gpio_loi():
    orig = sensors.Ultrasonic.__init__

    def boom(self, mock=False, mock_source=None, **k):
        if not mock:
            raise RuntimeError("không có GPIO")
        orig(self, mock=mock, mock_source=mock_source, **k)

    sensors.Ultrasonic.__init__ = boom
    try:
        hw = Hardware(mock=None, log=lambda *a: None)
        assert hw.mock is True
        hw.close()
    finally:
        sensors.Ultrasonic.__init__ = orig


def t_hardware_mock_false_phai_tao_du_thiet_bi():
    """Lỗi từng gặp trên Wokwi: Hardware(mock=False) để pir=None."""
    with Hardware(mock=False, log=lambda *a: None) as hw:
        assert hw.mock is False
        assert hw.ultrasonic is not None and hw.pir is not None and hw.leds is not None
        hw.leds.set_occupied(True)
        assert hw.leds._red.value() == 1 and hw.leds._green.value() == 0


def t_hardware_tu_dong_dung_gpio_that_khi_co_the():
    with Hardware(log=lambda *a: None) as hw:
        assert hw.mock is False and hw.leds is not None


# ------------------------------------------------------------- 2. hiển thị
def t_status_text():
    assert dsp.status_text(True) == dsp.TEXT_OCCUPIED
    assert dsp.status_text(False) == dsp.TEXT_EMPTY


def t_display_console_chi_in_khi_doi():
    out = []
    d = Display(console_only=True, log=out.append)
    d.start()
    d.update(1, False)
    d.update(1, False)
    d.update(2, True)
    d.close()
    assert len(out) == 2
    assert "Lượt: 2" in out[-1] and dsp.TEXT_OCCUPIED in out[-1]


def t_display_lcd_ghi_dung_chu():
    i2c = FakeI2C()
    d = Display(i2c=i2c, log=lambda *a: None)
    d.start()
    assert d.uses_window
    i2c.writes.clear()
    d.update(7, True)
    chars = "".join(chr(b) for rs, b in i2c.decoded() if rs)
    assert chars == "Luot: 7".ljust(16) + dsp.LCD_OCCUPIED.ljust(16), chars
    n = len(i2c.writes)
    d.update(7, True)                          # không đổi: không vẽ lại
    assert len(i2c.writes) == n
    d.update(8, False)
    assert d.shown == (8, dsp.LCD_EMPTY)
    d.close()
    assert not d.uses_window


def t_display_khong_co_lcd_thi_chuyen_console():
    out = []
    d = Display(i2c=FakeI2C(devices=[]), log=out.append)
    d.start()
    d.update(3, True)
    d.close()
    assert not d.uses_window
    assert any("Lượt: 3" in o for o in out)


# ------------------------------------------- chuỗi cảm biến -> LED/màn hình
def t_demo_dem_3_luot_cach_nhau_hon_1_giay():
    nen = [150.0] * 20
    qua = ([60.0] * 3 + [150.0] * 30) * 3          # mỗi lượt cách nhau ~1,6 giây
    res, disp, _ = chay_demo(nen + qua, [False], seconds=8)
    assert res["count"] == 3
    assert disp.calls[-1][0] == 3


def t_demo_hai_lan_chan_duoi_1_giay_chi_tinh_1():
    nen = [150.0] * 20
    qua = ([60.0] * 3 + [150.0] * 10) * 2          # cách nhau ~0,65 giây
    res, _, _ = chay_demo(nen + qua, [False], seconds=5)
    assert res["count"] == 1


def t_demo_dung_chan_cua_chi_dem_khi_vat_chan_di_khoi():
    nen = [150.0] * 20
    res, _, _ = chay_demo(nen + [60.0] * 100 + [150.0] * 5, [False], seconds=8)
    assert res["count"] == 1


def t_demo_pir_het_chuyen_dong_qua_timeout_thi_phong_trong():
    pir = [True] * 20 + [False]                    # có người 1 giây rồi im
    res, disp, leds_state = chay_demo([150.0], pir, seconds=5, timeout=2.0)
    trang_thai = [occ for _, occ in disp.calls]
    assert trang_thai[0] is False and True in trang_thai   # trống -> có người
    assert res["occupied"] is False and leds_state is False  # rồi lại trống (xanh)


def t_demo_pir_con_chuyen_dong_thi_giu_co_nguoi():
    res, _, leds_state = chay_demo([150.0], [True], seconds=5, timeout=2.0)
    assert res["occupied"] is True and leds_state is True


def t_record_in_csv_mock():
    n = ht.record(True, 0.3, None, 0.05)
    assert n >= 3


def run_all():
    tests = sorted((k, v) for k, v in globals().items() if k.startswith("t_") and callable(v))
    ok = 0
    for name, fn in tests:
        try:
            fn()
            ok += 1
            print("PASS", name)
        except Exception as exc:
            print("FAIL", name, "->", repr(exc))
    print("== %d/%d test đạt ==" % (ok, len(tests)))
    return ok == len(tests)


if __name__ == "__main__":
    run_all()
