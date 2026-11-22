"""main.py - Chọn chế độ chạy trên Wokwi (Raspberry Pi Pico, MicroPython).

Đổi MODE rồi bấm Run:
    "led"       nháy luân phiên đỏ/xanh
    "pir"       in ra khi PIR đổi trạng thái
    "distance"  in khoảng cách HC-SR04 mỗi 0,2 giây
    "display"   LCD đổi số và trạng thái mỗi giây
    "demo"      cảm biến -> đếm lượt tạm -> LED + LCD (bài test chính)
    "record"    in CSV t_sec,distance_cm,pir ra Serial
    "selftest"  chạy toàn bộ test tự động (mock, không cần chạm vào mạch)
"""
import hardware_test as ht

MODE = "demo"
MOCK = False          # True = bỏ qua mạch, dùng dữ liệu giả
DEMO_TIMEOUT = 10     # giây không có chuyển động thì coi là trống (thật: 300). 10 để test cho nhanh
RECORD_SECONDS = 30

if MODE == "led":
    ht.test_led(MOCK)
elif MODE == "pir":
    ht.test_pir(MOCK)
elif MODE == "distance":
    ht.test_distance(MOCK)
elif MODE == "display":
    ht.test_display(MOCK)
elif MODE == "demo":
    ht.demo(mock=MOCK, timeout=DEMO_TIMEOUT)
elif MODE == "record":
    ht.record(MOCK, RECORD_SECONDS)
elif MODE == "selftest":
    import test_hardware
    test_hardware.run_all()
else:
    print("MODE không hợp lệ:", MODE)
