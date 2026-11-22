"""hardware_test.py - Test từng linh kiện, chạy thử cả chuỗi, ghi dữ liệu đo thô (MicroPython).

Trên Wokwi không gõ lệnh được nên chọn chế độ bằng biến MODE trong main.py.
Các hàm bên dưới giống bản gốc tools/hardware_test.py. Bấm nút Stop để dừng.

Lưu ý: bộ đếm trong `run_demo` chỉ để kiểm tra phần cứng ở tuần 1. Thuật toán
chính thức là counter.py của C; không dùng lẫn.
"""
import time

from sensors import Hardware, Leds, Pir, Ultrasonic, now


def median(values):
    s = sorted(values)
    return s[len(s) // 2]


def stamp():
    t = time.localtime()
    return "%02d:%02d:%02d" % (t[3], t[4], t[5])


def test_led(mock=False):
    leds = Leds(mock=mock)
    try:
        print("Nháy luân phiên LED đỏ / xanh (Stop để dừng)")
        state = False
        while True:
            state = not state
            leds.set_occupied(state)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        leds.close()


def test_pir(mock=False, warmup=3):
    pir = Pir(mock=mock)
    print("PIR khởi động %d giây (PIR thật cần 30-60 giây)..." % warmup)
    pir.wait_ready(warmup, on_tick=lambda r: print("  còn %ds" % r))
    print("Bắt đầu đọc. Bấm vào PIR trong Wokwi để giả lập chuyển động")
    try:
        last = None
        while True:
            m = pir.motion()
            if m != last:
                print(stamp(), "CÓ chuyển động" if m else "Không còn chuyển động")
                last = m
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        pir.close()


def test_distance(mock=False):
    us = Ultrasonic(mock=mock)
    print("Đo khoảng cách (cm). Kéo thanh Distance của HC-SR04 trong Wokwi")
    try:
        while True:
            print("%6.1f cm" % us.read_cm())
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        us.close()


def test_display(mock=False):
    from display import Display
    disp = Display(console_only=mock)
    disp.start()
    print("Màn hình đổi số và trạng thái mỗi giây")
    try:
        n = 0
        while True:
            n += 1
            disp.update(n, occupied=(n % 4 < 2))
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        disp.close()


def run_demo(hw, display, seconds=None, interval=0.05, drop_ratio=0.7,
             min_gap=1.0, timeout=300.0, clock=now, sleep=time.sleep,
             log=print):
    """Chạy thử chuỗi: HC-SR04 -> đếm lượt tạm -> LED + màn hình; PIR -> trạng thái phòng.

    - Khoảng cách nền = trung vị của 10 lần đo đầu (đừng chắn trước cảm biến lúc này).
    - Khoảng cách < nền * drop_ratio rồi trở lại = 1 lượt.
    - Hai lượt cách nhau dưới min_gap giây chỉ tính 1.
    - Quá `timeout` giây không thấy chuyển động = phòng trống.
    Trả về dict kết quả. clock/sleep truyền vào được để test không phải chờ thật.
    """
    base = []
    for _ in range(10):
        base.append(hw.ultrasonic.read_cm())
        sleep(interval)
    baseline = median(base)
    threshold = baseline * drop_ratio
    log("Khoảng cách nền: %.1f cm, ngưỡng chắn: %.1f cm" % (baseline, threshold))

    count, blocked = 0, False
    last_count_t, last_motion_t = -1e9, -1e9
    occupied = False
    hw.leds.set_occupied(occupied)
    display.update(count, occupied)

    t_end = None if seconds is None else clock() + seconds
    while t_end is None or clock() < t_end:
        t = clock()
        d = hw.ultrasonic.read_cm()
        if d < threshold:
            blocked = True
        elif blocked:                       # vật chắn vừa đi khỏi
            blocked = False
            if t - last_count_t >= min_gap:
                count += 1
                last_count_t = t
                log("%s  +1 lượt  (tổng %d)" % (stamp(), count))
                display.update(count, occupied)

        if hw.pir.motion():
            last_motion_t = t
        moi = (t - last_motion_t) < timeout
        if moi != occupied:
            occupied = moi
            hw.leds.set_occupied(occupied)
            display.update(count, occupied)
            log("PHÒNG: " + ("CÓ NGƯỜI (đỏ)" if occupied else "TRỐNG (xanh)"))
        sleep(interval)
    return {"count": count, "occupied": occupied, "baseline": baseline}


def demo(mock=None, seconds=None, timeout=300.0, warmup=3):
    from display import Display
    hw = Hardware(mock=mock)
    disp = Display(console_only=hw.mock)
    disp.start()
    if not hw.mock:
        print("Chờ PIR khởi động %d giây..." % warmup)
        hw.pir.wait_ready(warmup)
    print("Đo khoảng cách nền: đừng kéo thanh Distance lúc này.")
    try:
        res = run_demo(hw, disp, seconds=seconds, timeout=timeout)
        print("Kết quả:", res)
    except KeyboardInterrupt:
        pass
    finally:
        disp.close()
        hw.close()


def record(mock=False, seconds=60, out=None, interval=0.05):
    """In CSV (t_sec,distance_cm,pir) ra serial; ghi thêm vào file nếu có `out`.
    Wokwi không giữ file sau khi dừng nên copy từ cửa sổ Serial Monitor."""
    us = Ultrasonic(mock=mock)
    pir = Pir(mock=mock)
    f = open(out, "w") if out else None
    header = "t_sec,distance_cm,pir"
    print(header)
    if f:
        f.write(header + "\n")
    t0 = now()
    n = 0
    try:
        while now() - t0 < seconds:
            line = "%.3f,%.1f,%d" % (now() - t0, us.read_cm(), int(pir.motion()))
            print(line)
            if f:
                f.write(line + "\n")
            n += 1
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        us.close()
        pir.close()
        if f:
            f.close()
    print("Xong: %d dòng" % n)
    return n
