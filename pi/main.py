"""Main loop for the Raspberry Pi door counter.

Run with real hardware: ``python -m pi.main``
Run a laptop smoke check: ``python -m pi.main --mock --no-server --seconds 3 --console``
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time

from . import config as cfg
from .client import ServerClient
from .counter import Counter
from .display import Display
from .room_state import RoomState
from .sensors import Hardware

log = logging.getLogger("pi.main")


def run(
    hw,
    display,
    client,
    counter=None,
    room=None,
    interval=cfg.SAMPLE_INTERVAL_S,
    seconds=None,
    pir_warmup=cfg.PIR_WARMUP_S,
    stop=None,
    clock=time.monotonic,
    sleep=time.sleep,
    wall=time.time,
):
    """Read sensors and update the counter, room state, outputs and server queue."""
    counter = counter if counter is not None else Counter()
    room = room if room is not None else RoomState()
    stats = {"samples": 0, "passes": 0, "resets": 0, "errors": 0, "state_changes": 0}

    hw.leds.show_room(room.occupied)
    display.update(counter.count, room.occupied)
    client.send_state(room.occupied, wall(), motion=False, local_count=counter.count)

    t0 = clock()
    next_t = t0
    while True:
        now = clock()
        if (stop is not None and stop.is_set()) or (seconds is not None and now - t0 >= seconds):
            break
        try:
            distance = hw.ultrasonic.read_cm()
            if counter.update(distance, now):
                stats["passes"] += 1
                log.info("+1 lượt (tổng local %d)", counter.count)
                client.send_event(total=counter.count, ts=wall())
                display.update(counter.count, room.occupied)

            motion = False
            if now - t0 >= pir_warmup:
                motion = hw.pir.motion()
                if room.update(motion, now):
                    stats["state_changes"] += 1
                    log.info("Phòng: %s", "CÓ NGƯỜI (đỏ)" if room.occupied else "TRỐNG (xanh)")
                    hw.leds.show_room(room.occupied)
                    display.update(counter.count, room.occupied)
                    client.send_state(
                        room.occupied,
                        wall(),
                        motion=motion,
                        local_count=counter.count,
                        distance_cm=distance,
                    )

            commands = client.consume_commands()
            for command in commands:
                if command.get("command") == "reset_counter":
                    counter.reset()
                    stats["resets"] += 1
                    client.ack_command(command["id"], "success", "Bộ đếm Pi đã về 0")
                    display.update(counter.count, room.occupied)
                    log.info("Đã nhận lệnh reset #%s từ server", command["id"])
                else:
                    client.ack_command(command["id"], "failed", "Lệnh không được hỗ trợ trên Pi")

            # Dùng số server làm chuẩn sau khi hàng đợi đã gửi xong (gồm cả chống dội phía server).
            server_count = getattr(client, "server_count", None)
            if server_count is not None and client.pending == 0 and counter.count != server_count:
                counter.count = server_count
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
            next_t = clock()
    stats["count"] = counter.count
    stats["occupied"] = room.occupied
    return stats


def build_parser():
    parser = argparse.ArgumentParser(description="Đếm lượt người qua cửa (Raspberry Pi)")
    parser.add_argument("--mock", action="store_true", help="dùng cảm biến giả để chạy trên laptop")
    parser.add_argument("--no-server", action="store_true", help="không gửi dữ liệu lên backend")
    parser.add_argument("--api-url", default=cfg.API_URL, help="địa chỉ backend FastAPI")
    parser.add_argument("--api-key", default=cfg.API_KEY, help="API key; ưu tiên dùng biến môi trường API_KEY")
    parser.add_argument("--seconds", type=float, default=None, help="chạy trong số giây đã chọn rồi dừng")
    parser.add_argument("--console", action="store_true", help="chỉ in trạng thái, không mở LCD")
    parser.add_argument("--drop-ratio", type=float, default=cfg.DROP_RATIO)
    parser.add_argument("--min-gap", type=float, default=cfg.MIN_GAP_S)
    parser.add_argument("--pir-timeout", type=float, default=cfg.PIR_TIMEOUT_S)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        hw = Hardware(mock=args.mock)
    except Exception as exc:
        log.error("Không khởi tạo được GPIO: %s", exc)
        log.error("Cài gói trong pi/requirements.txt và kiểm tra chân BCM trong docs/HARDWARE.md")
        return 2

    display = Display(console_only=bool(args.console or args.mock))
    client = ServerClient(base_url=args.api_url, api_key=args.api_key, enabled=not args.no_server)
    counter = Counter(drop_ratio=args.drop_ratio, min_gap_s=args.min_gap)
    if client.enabled:
        state = client.fetch_state()
        if state and isinstance(state.get("count_today"), int):
            counter.count = state["count_today"]
            log.info("Khôi phục số đếm từ server: %d", counter.count)

    stop = threading.Event()
    previous_term = None
    try:
        if hasattr(signal, "SIGTERM"):
            previous_term = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
        display.start()
        client.start()
        log.info("Bắt đầu: %s; backend: %s", "MOCK" if args.mock else "PHẦN CỨNG THẬT", "TẮT" if args.no_server else args.api_url)
        stats = run(
            hw,
            display,
            client,
            counter=counter,
            room=RoomState(timeout_s=args.pir_timeout),
            seconds=args.seconds,
            stop=stop,
            pir_warmup=0.0 if args.mock else cfg.PIR_WARMUP_S,
        )
    except KeyboardInterrupt:
        log.info("Dừng theo yêu cầu")
        stats = None
    finally:
        try:
            hw.leds.all_off()
        finally:
            client.close()
            display.close()
            hw.close()
            if previous_term is not None:
                signal.signal(signal.SIGTERM, previous_term)
    if stats is not None:
        log.info("Kết thúc: %s", stats)
        print("Kết quả:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
