from __future__ import annotations

from pi.display import Display, Leds
from pi.sensors import Hardware, create_sensors


def test_mock_sensors_follow_scripted_inputs():
    ultrasonic, pir = create_sensors(True, ultrasonic_source=[150, 60], pir_source=[True, False])
    try:
        assert ultrasonic.read_cm() == 150
        assert ultrasonic.read_cm() == 60
        assert ultrasonic.read_cm() == 60  # giữ mẫu cuối khi kịch bản hết
        assert pir.motion() is True
        assert pir.motion() is False
        assert pir.motion() is False
    finally:
        ultrasonic.close()
        pir.close()


def test_mock_hardware_and_console_display_do_not_need_gpio():
    output = []
    with Hardware(mock=True, ultrasonic_source=[120], pir_source=[True]) as hardware:
        assert hardware.ultrasonic.read_cm() == 120
        assert hardware.pir.motion() is True
        hardware.leds.show_room(True)
        assert hardware.leds.state is True
    display = Display(console_only=True, log=output.append)
    display.start()
    display.update(2, True)
    display.update(2, True)
    display.update(3, False)
    display.close()
    assert len(output) == 2
    assert "Lượt: 2" in output[0] and "CÓ NGƯỜI" in output[0]
    assert "Lượt: 3" in output[1] and "PHÒNG TRỐNG" in output[1]
