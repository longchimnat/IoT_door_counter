"""[Leader / Người A] Test trạng thái phòng. Chạy:  pytest -q"""
from pi.room_state import RoomState


def test_room_empty_after_timeout():
    r = RoomState(timeout_seconds=300)
    assert r.update(True, 0) is True and r.occupied
    assert r.update(False, 299) is False and r.occupied
    assert r.update(False, 301) is True and not r.occupied


def test_room_starts_empty_without_motion():
    r = RoomState(timeout_seconds=300)
    assert r.update(False, 1000) is False and not r.occupied
