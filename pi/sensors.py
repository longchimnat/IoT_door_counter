"""HC-SR04 and PIR drivers with deterministic laptop mocks."""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable

from . import config as cfg
from .display import Leds

log = logging.getLogger(__name__)


class UltrasonicSensor:
    """Read HC-SR04 distance in centimetres using BCM GPIO pins."""

    def __init__(self, mock: bool = False, mock_source: Iterable[float] | None = None):
        self.mock = mock
        self._source = iter(mock_source) if mock_source is not None else None
        self._last_mock = cfg.MAX_DISTANCE_CM
        self._started = time.monotonic()
        self._trigger = self._echo = None
        if not mock:
            from gpiozero import DigitalInputDevice, DigitalOutputDevice

            self._trigger = DigitalOutputDevice(cfg.TRIG_PIN, initial_value=False)
            try:
                self._echo = DigitalInputDevice(cfg.ECHO_PIN, pull_up=False)
            except Exception:
                self._trigger.close()
                self._trigger = None
                raise

    def read_cm(self) -> float | None:
        if self.mock:
            if self._source is not None:
                try:
                    value = next(self._source)
                    if value is not None:
                        self._last_mock = min(max(float(value), 0.0), cfg.MAX_DISTANCE_CM)
                except StopIteration:
                    pass
                return self._last_mock
            # Một lượt đi qua ngắn mỗi 8 giây để kiểm tra end-to-end ở chế độ mock.
            phase = (time.monotonic() - self._started) % 8.0
            return 60.0 if 1.0 <= phase < 1.35 else 150.0

        assert self._trigger is not None and self._echo is not None
        self._trigger.off()
        time.sleep(0.000002)
        self._trigger.on()
        time.sleep(0.00001)
        self._trigger.off()

        deadline = time.monotonic() + cfg.ECHO_TIMEOUT_S
        while not self._echo.value:
            if time.monotonic() >= deadline:
                return cfg.MAX_DISTANCE_CM
        pulse_start = time.monotonic()
        deadline = pulse_start + cfg.ECHO_TIMEOUT_S
        while self._echo.value:
            if time.monotonic() >= deadline:
                return cfg.MAX_DISTANCE_CM
        pulse_end = time.monotonic()
        distance = (pulse_end - pulse_start) * 17150.0
        if distance < cfg.MIN_VALID_CM:
            return None
        return min(distance, cfg.MAX_DISTANCE_CM)

    def close(self) -> None:
        for device in (self._echo, self._trigger):
            if device is not None:
                device.close()
        self._echo = self._trigger = None


class PirSensor:
    """Read a PIR motion sensor."""

    def __init__(self, mock: bool = False, mock_source: Iterable[bool] | None = None):
        self.mock = mock
        self._source = iter(mock_source) if mock_source is not None else None
        self._last_mock = False
        self._sensor = None
        if not mock:
            from gpiozero import MotionSensor

            self._sensor = MotionSensor(cfg.PIR_PIN, queue_len=1)

    def motion(self) -> bool:
        if self.mock:
            if self._source is not None:
                try:
                    self._last_mock = bool(next(self._source))
                except StopIteration:
                    pass
            return self._last_mock
        return bool(self._sensor.motion_detected)

    def close(self) -> None:
        if self._sensor is not None:
            self._sensor.close()
            self._sensor = None


def create_sensors(mock: bool = False, *, ultrasonic_source=None, pir_source=None):
    ultrasonic = UltrasonicSensor(mock=mock, mock_source=ultrasonic_source)
    try:
        pir = PirSensor(mock=mock, mock_source=pir_source)
    except Exception:
        ultrasonic.close()
        raise
    return ultrasonic, pir


class Hardware:
    """Own all Pi inputs and LEDs; passing mock=True never touches GPIO."""

    def __init__(self, mock: bool = False, ultrasonic_source=None, pir_source=None):
        self.mock = bool(mock)
        self.ultrasonic = self.pir = self.leds = None
        try:
            self.ultrasonic, self.pir = create_sensors(
                self.mock, ultrasonic_source=ultrasonic_source, pir_source=pir_source
            )
            self.leds = Leds(mock=self.mock)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.leds is not None:
            self.leds.close()
        if self.pir is not None:
            self.pir.close()
        if self.ultrasonic is not None:
            self.ultrasonic.close()
        self.leds = self.pir = self.ultrasonic = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False
