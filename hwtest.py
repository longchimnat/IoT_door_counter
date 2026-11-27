"""Test từng linh kiện: python hwtest.py led|pir|dist|lcd  (Ctrl+C để dừng)"""
import sys
import time

from pi import config as cfg


def led():
    from gpiozero import LED
    leds = {"xanh": LED(cfg.LED_GREEN_PIN), "do": LED(cfg.LED_RED_PIN)}
    try:
        for name, d in leds.items():
            print(f"LED {name} sáng 3 giây")
            d.on(); time.sleep(3); d.off()
    finally:
        for d in leds.values():
            d.close()


def pir():
    from gpiozero import MotionSensor
    s = MotionSensor(cfg.PIR_PIN)
    print("Đợi PIR ổn định 30 giây, đừng cử động...")
    time.sleep(30)
    print("Vẫy tay trước PIR (Ctrl+C để dừng)")
    try:
        while True:
            print("CÓ chuyển động" if s.motion_detected else "yên")
            time.sleep(0.5)
    finally:
        s.close()


def dist():
    from gpiozero import DistanceSensor
    s = DistanceSensor(echo=cfg.ECHO_PIN, trigger=cfg.TRIG_PIN, max_distance=2)
    try:
        while True:
            print(f"{s.distance * 100:.1f} cm")
            time.sleep(0.3)
    finally:
        s.close()


def lcd():
    from RPLCD.i2c import CharLCD
    d = CharLCD("PCF8574", cfg.LCD_I2C_ADDRESS, port=cfg.LCD_I2C_PORT,
                cols=cfg.LCD_COLUMNS, rows=cfg.LCD_ROWS)
    d.clear(); d.write_string("Xin chao"); d.crlf(); d.write_string("Door counter")
    time.sleep(5)
    d.clear()


if __name__ == "__main__":
    tests = {"led": led, "pir": pir, "dist": dist, "lcd": lcd}
    if len(sys.argv) != 2 or sys.argv[1] not in tests:
        sys.exit("Dùng: python hwtest.py led|pir|dist|lcd")
    try:
        tests[sys.argv[1]]()
    except KeyboardInterrupt:
        print("\nDừng.")
