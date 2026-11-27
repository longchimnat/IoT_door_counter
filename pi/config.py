"""Cấu hình thiết bị Pi. Các giá trị có thể ghi đè qua biến môi trường."""
from __future__ import annotations

import os


def _value(name: str, default, cast=None):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        if cast is not None:
            return cast(raw)
        return type(default)(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Giá trị biến môi trường {name} không hợp lệ: {raw!r}") from exc


# BCM GPIO: đối chiếu sơ đồ chân Raspberry Pi trong docs/HARDWARE.md.
TRIG_PIN = _value("TRIG_PIN", 23)
ECHO_PIN = _value("ECHO_PIN", 24)
PIR_PIN = _value("PIR_PIN", 17)
LED_GREEN_PIN = _value("LED_GREEN_PIN", 27)
LED_RED_PIN = _value("LED_RED_PIN", 22)

LCD_I2C_ADDRESS = _value("LCD_I2C_ADDRESS", 0x27, lambda s: int(s, 0))
LCD_I2C_PORT = _value("LCD_I2C_PORT", 1)
LCD_COLUMNS = _value("LCD_COLUMNS", 16)
LCD_ROWS = _value("LCD_ROWS", 2)

MAX_DISTANCE_CM = _value("MAX_DISTANCE_CM", 200.0)
MIN_VALID_CM = _value("MIN_VALID_CM", 2.0)
SAMPLE_INTERVAL_S = _value("SAMPLE_INTERVAL_S", 0.05)
ECHO_TIMEOUT_S = _value("ECHO_TIMEOUT_S", 0.03)

DROP_RATIO = _value("DROP_RATIO", 0.70)
RETURN_RATIO = _value("RETURN_RATIO", 0.85)
MIN_GAP_S = _value("MIN_GAP_S", 1.0)
DEBOUNCE_SAMPLES = _value("DEBOUNCE_SAMPLES", 2)
MAX_BLOCK_S = _value("MAX_BLOCK_S", 8.0)
BASELINE_SAMPLES = _value("BASELINE_SAMPLES", 15)
BASELINE_ALPHA = _value("BASELINE_ALPHA", 0.02)
FAR_RATIO = _value("FAR_RATIO", 1.20)
REBASE_SAMPLES = _value("REBASE_SAMPLES", 10)

PIR_TIMEOUT_S = _value("PIR_TIMEOUT_S", 300.0)
PIR_WARMUP_S = _value("PIR_WARMUP_S", 30.0)

API_URL = _value("API_URL", "http://127.0.0.1:8000")
API_KEY = _value("API_KEY", "")
DEVICE_ID = _value("DEVICE_ID", "door-01")
HTTP_TIMEOUT_S = _value("HTTP_TIMEOUT_S", 3.0)
SEND_RETRY_INTERVAL_S = _value("SEND_RETRY_INTERVAL_S", 5.0)
COMMAND_POLL_INTERVAL_S = _value("COMMAND_POLL_INTERVAL_S", 2.0)
STATE_HEARTBEAT_S = _value("STATE_HEARTBEAT_S", 10.0)
QUEUE_FILE = _value("QUEUE_FILE", "data/pending_events.jsonl")
MAX_QUEUE = _value("MAX_QUEUE", 50000)
