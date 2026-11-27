"""Test cảm biến sóng âm HC-SR04 bằng ĐÚNG driver và bộ đếm của chương trình chính.

Đặt file này trong thư mục ~/IoT_Door_Counter (cùng cấp với thư mục pi/). Chạy:

    python sonic_test.py raw       # bước 1: chỉ in khoảng cách, kiểm tra cảm biến đo được chưa
    python sonic_test.py count     # bước 2: chạy bộ đếm thật, xem đi qua có được đếm không
    python sonic_test.py count --seconds 30      # tự dừng sau 30 giây

Dừng bằng Ctrl+C. Cuối cùng in bản tóm tắt và gợi ý nguyên nhân nếu không đếm được.
(Thêm --mock để thử script trên laptop không có cảm biến.)
"""
import argparse
import statistics
import time

from pi import config as cfg
from pi.counter import BLOCKED, CALIBRATING, IDLE, Counter
from pi.sensors import UltrasonicSensor

TIMEOUT_CM = cfg.MAX_DISTANCE_CM - 0.01  # driver trả về giá trị này khi không nhận được echo


def describe(d):
    if d is None:
        return "đo lỗi (quá gần, dưới 2 cm)"
    if d >= TIMEOUT_CM:
        return f"{d:6.1f} cm  <-- KHÔNG THẤY ECHO hoặc vật quá xa"
    return f"{d:6.1f} cm"


def run_raw(sensor, seconds):
    print("RAW: in khoảng cách. Đặt tay hoặc tấm bìa trước cảm biến cách 20, 50, 100 cm,")
    print("so với thước. Mục tiêu: số cm đổi theo vị trí vật. Ctrl+C để dừng.\n")
    start = time.monotonic()
    n = timeouts = 0
    try:
        while seconds is None or time.monotonic() - start < seconds:
            d = sensor.read_cm()
            n += 1
            if d is not None and d >= TIMEOUT_CM:
                timeouts += 1
            print(describe(d))
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    print(f"\nTóm tắt: {n} lần đo, {timeouts} lần không có echo.")
    if n and timeouts / n > 0.8:
        print("=> Hầu như không có echo: kiểm tra dây TRIG/ECHO, nguồn 5V, cầu phân áp ECHO,")
        print("   và cảm biến có hướng về phía có vật cách dưới 2 mét không.")


def bar(d, base, width=30):
    if not base:
        return ""
    ratio = max(0.0, min(1.5, d / base))
    return "#" * int(ratio / 1.5 * width)


def run_count(sensor, seconds):
    counter = Counter()
    print("Bước 1: giữ lối đi TRỐNG, đứng ra ngoài tầm nhìn của cảm biến trong 3 giây để đo nền...")
    time.sleep(3)
    print("Đang chạy. Đi qua trước cảm biến vài lần, cách nhau trên 1 giây. Ctrl+C để dừng.\n")

    start = time.monotonic()
    total = timeouts = invalid = 0
    lo = hi = None
    last_print = 0.0
    try:
        while seconds is None or time.monotonic() - start < seconds:
            now = time.monotonic()
            d = sensor.read_cm()
            total += 1
            if d is None:
                invalid += 1
            else:
                if d >= TIMEOUT_CM:
                    timeouts += 1
                if counter.baseline is not None:
                    lo = d if lo is None else min(lo, d)
                    hi = d if hi is None else max(hi, d)
            if counter.update(d, now):
                print(f"\n>>> +1 LƯỢT  (tổng {counter.count})")

            if now - last_print >= 0.2 and d is not None:
                last_print = now
                base = counter.baseline
                if counter.state == CALIBRATING or base is None:
                    line = f"đang đo nền... {d:6.1f} cm"
                else:
                    limit = base * cfg.DROP_RATIO
                    state = {IDLE: "trống   ", BLOCKED: "BỊ CHẮN "}.get(counter.state, counter.state)
                    line = (f"{d:6.1f} cm | nền {base:5.1f} | chắn khi < {limit:5.1f} | "
                            f"{state}| lượt {counter.count:3d} | {bar(d, base)}")
                print(line.ljust(110), end="\r", flush=True)
            time.sleep(cfg.SAMPLE_INTERVAL_S)
    except KeyboardInterrupt:
        pass

    print("\n\n===== TÓM TẮT =====")
    print(f"Số mẫu: {total} | không có echo: {timeouts} | đo lỗi: {invalid}")
    print(f"Khoảng cách nền: {counter.baseline if counter.baseline is None else round(counter.baseline, 1)} cm")
    if lo is not None:
        print(f"Sau khi đo nền, thấp nhất {lo:.1f} cm, cao nhất {hi:.1f} cm")
    print(f"Số lượt đếm được: {counter.count}")
    explain(counter, total, timeouts, lo)


def explain(counter, total, timeouts, lo):
    if counter.count > 0:
        print("=> Bộ đếm hoạt động. Nếu đếm thiếu/thừa, chỉnh vị trí cảm biến hoặc DROP_RATIO.")
        return
    if total and timeouts / total > 0.8:
        print("=> Gần như không nhận được echo, nên không thể đếm.")
        print("   Kiểm tra: dây TRIG (GPIO23) và ECHO (GPIO24 qua 1 kΩ + 2 kΩ), nguồn 5V, GND chung,")
        print("   và cảm biến phải hướng về phía có tường hoặc vật cách dưới 2 mét.")
    elif counter.baseline is None:
        print("=> Chưa đo xong khoảng cách nền (không đủ mẫu hợp lệ). Chạy lâu hơn một chút.")
    elif lo is not None and lo >= counter.baseline * cfg.DROP_RATIO:
        print(f"=> Khoảng cách thấp nhất ({lo:.1f} cm) không xuống dưới ngưỡng "
              f"{counter.baseline * cfg.DROP_RATIO:.1f} cm, nên không bị coi là bị chắn.")
        print("   Cách xử lý: để cảm biến chĩa ngang lối đi, ngang hông người, hướng vào tường hoặc")
        print("   khung cửa đối diện cách khoảng 80 đến 120 cm (người đi qua phải gần cảm biến hơn nền")
        print("   ít nhất 30%). Hoặc thử tạm DROP_RATIO=0.85, ví dụ:  DROP_RATIO=0.85 python sonic_test.py count")
    else:
        print("=> Có bị chắn nhưng không được tính là một lượt. Có thể vật đứng yên quá lâu hoặc hai lần")
        print("   chắn cách nhau dưới 1 giây. Đi qua dứt khoát rồi rời khỏi tầm nhìn.")


def main():
    parser = argparse.ArgumentParser(description="Test HC-SR04 và bộ đếm")
    parser.add_argument("mode", nargs="?", choices=["raw", "count"], default="count")
    parser.add_argument("--seconds", type=float, default=None, help="tự dừng sau N giây")
    parser.add_argument("--mock", action="store_true", help="dùng cảm biến giả lập (không cần Pi)")
    args = parser.parse_args()

    sensor = UltrasonicSensor(mock=args.mock)
    try:
        if args.mode == "raw":
            run_raw(sensor, args.seconds)
        else:
            run_count(sensor, args.seconds)
    finally:
        sensor.close()


if __name__ == "__main__":
    main()
