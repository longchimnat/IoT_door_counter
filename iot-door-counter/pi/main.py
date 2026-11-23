"""main.py - Chương trình chính chạy trên Raspberry Pi.

Người phụ trách: A (Long).

    python -m pi.main                       # chạy thật trên Pi
    python -m pi.main --mock                # cảm biến giả, chạy được trên laptop
    python -m pi.main --mock --no-server    # không gửi lên server
    python -m pi.main --api-url http://192.168.1.50:5000

Mỗi vòng (SAMPLE_INTERVAL_S): đọc HC-SR04 -> Counter (đếm lượt) -> màn hình + gửi server;
đọc PIR -> RoomState (có người/trống) -> LED + màn hình + gửi server; nhận lệnh reset từ web.
Gửi mạng chạy ở luồng riêng nên mạng chậm không làm sót lượt.
Một lần đọc cảm biến lỗi chỉ ghi log, không làm chương trình dừng.
"""
import argparse
import logging
import signal
import sys
import threading
import time

from pi import config as cfg
from pi.client import ServerClient
from pi.counter import Counter
from pi.display import Display
from pi.room_state import RoomState
from pi.sensors import Hardware

log = logging.getLogger("pi.main")


def run(hw, display, client, counter=None, room=None, interval=cfg.SAMPLE_INTERVAL_S,
        seconds=None, pir_warmup=cfg.PIR_WARMUP_S, stop=None,
        clock=time.monotonic, sleep=time.sleep, wall=time.time):
    """Vòng chạy chính. Trả về dict thống kê. clock/sleep/wall truyền vào được để test."""
    counter = counter if counter is not None else Counter()
    room = room if room is not None else RoomState()
    stats = {"samples": 0, "passes": 0, "resets": 0, "errors": 0, "state_changes": 0}

    hw.leds.set_occupied(room.occupied)
    display.update(counter.count, room.occupied)
    client.send_state(room.occupied, wall())

    t0 = clock()
    next_t = t0
    while True:
        now = clock()
        if stop is not None and stop.is_set():
            break
        if seconds is not None and now - t0 >= seconds:
            break
        try:
            if counter.update(hw.ultrasonic.read_cm(), now):
                stats["passes"] += 1
                log.info("+1 lượt (tổng %d)", counter.count)
                client.send_event(total=counter.count, ts=wall())
                display.update(counter.count, room.occupied)

            if now - t0 >= pir_warmup and room.update(hw.pir.motion(), now):
                stats["state_changes"] += 1
                log.info("Phòng: %s", "CÓ NGƯỜI (đỏ)" if room.occupied else "TRỐNG (xanh)")
                hw.leds.set_occupied(room.occupied)
                display.update(counter.count, room.occupied)
                client.send_state(room.occupied, wall())

            if client.consume_reset():
                counter.reset()
                stats["resets"] += 1
                log.info("Web yêu cầu reset: về 0")
                display.update(counter.count, room.occupied)
        except Exception:
            stats["errors"] += 1
            log.exception("Lỗi trong vòng đọc cảm biến (bỏ qua, chạy tiếp)")
        stats["samples"] += 1

        next_t += interval
        delay = next_t - clock()
        if delay > 0:
            sleep(delay)
        else:
            next_t = clock()          # trễ nhịp thì không dồn bù
    stats["count"] = counter.count
    stats["occupied"] = room.occupied
    return stats


def build_parser():
    p = argparse.ArgumentParser(description="Đếm lượt người qua cửa (Raspberry Pi)")
    p.add_argument("--mock", action="store_true", help="dùng cảm biến giả (không cần phần cứng)")
    p.add_argument("--no-server", action="store_true", help="không gửi dữ liệu lên server")
    p.add_argument("--api-url", default=cfg.API_URL, help="địa chỉ server (mặc định theo config)")
    p.add_argument("--seconds", type=float, default=None, help="chạy bấy nhiêu giây rồi dừng")
    p.add_argument("--windowed", action="store_true", help="màn hình dạng cửa sổ, không toàn màn hình")
    p.add_argument("--console", action="store_true", help="không mở cửa sổ, chỉ in ra console")
    p.add_argument("--drop-ratio", type=float, default=cfg.DROP_RATIO)
    p.add_argument("--min-gap", type=float, default=cfg.MIN_GAP_S)
    p.add_argument("--pir-timeout", type=float, default=cfg.PIR_TIMEOUT_S,
                   help="giây không chuyển động thì coi là phòng trống (mặc định 300)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        hw = Hardware(mock=bool(args.mock))
    except Exception as exc:
        log.error("Không khởi tạo được phần cứng: %s", exc)
        log.error("Chạy trên Raspberry Pi thật, hoặc thêm --mock. Nếu lỗi lgpio: "
                  "sudo apt install python3-gpiozero python3-lgpio")
        return 2

    display = Display(fullscreen=not (args.mock or args.windowed), console_only=args.console)
    client = ServerClient(base_url=args.api_url, enabled=not args.no_server)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())     # systemd dừng dịch vụ

    log.info("Bắt đầu: %s, server: %s", "MOCK" if args.mock else "PHẦN CỨNG THẬT",
             "TẮT" if not client.enabled else args.api_url)
    stats = None
    try:
        display.start()
        client.start()
        stats = run(hw, display, client,
                    counter=Counter(drop_ratio=args.drop_ratio, min_gap_s=args.min_gap),
                    room=RoomState(timeout_s=args.pir_timeout),
                    seconds=args.seconds, stop=stop,
                    pir_warmup=0.0 if args.mock else cfg.PIR_WARMUP_S)
    except KeyboardInterrupt:
        log.info("Dừng theo yêu cầu (Ctrl+C)")
    finally:
        try:
            hw.leds.all_off()
        finally:
            client.close()
            display.close()
            hw.close()
    if stats is not None:
        log.info("Kết thúc: %s", stats)
        print("Kết quả:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
