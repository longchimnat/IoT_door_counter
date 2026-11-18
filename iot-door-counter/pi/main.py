"""[Leader] Chương trình chính trên Pi: ghép các module lại.

Chạy thử không cần phần cứng :  python -m pi.main --mock
Chạy thật trên Pi            :  python -m pi.main
"""
import argparse
import time

from . import config
from .client import ApiClient
from .counter import DoorCounter
from .display import create_outputs
from .room_state import RoomState
from .sensors import create_sensors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="dùng cảm biến giả lập")
    args = ap.parse_args()

    ultra, pir = create_sensors(mock=args.mock)
    leds, lcd = create_outputs(mock=args.mock)
    counter = DoorCounter()
    room = RoomState()
    api = ApiClient()

    def refresh_outputs():
        leds.show_room(room.occupied)
        lcd.show(counter.count, room.occupied)

    refresh_outputs()
    api.send_event("room_status", room_status="empty")
    print(f"Đang đo nền ({config.BASELINE_SAMPLES} mẫu) - giữ cửa trống...")
    last_poll = 0.0

    try:
        while True:
            now = time.monotonic()

            if counter.update(ultra.read_cm(), now):
                print(f"+1 lượt (tổng {counter.count})")
                api.send_event("pass", count_today=counter.count)
                refresh_outputs()

            if room.update(pir.motion(), now):
                api.send_event("room_status",
                               room_status="occupied" if room.occupied else "empty")
                refresh_outputs()

            if now - last_poll >= config.COMMAND_POLL_INTERVAL:
                last_poll = now
                for cmd in api.fetch_commands():
                    if cmd.get("type") == "reset":
                        counter.reset()
                        print("Nhận lệnh reset từ web")
                        refresh_outputs()

            time.sleep(config.SAMPLE_INTERVAL)
    except KeyboardInterrupt:
        print("\nDừng chương trình.")


if __name__ == "__main__":
    main()
