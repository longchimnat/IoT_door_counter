"""Kiểm thử trạng thái phòng (pi/room_state.py). Chạy: python -m pytest tests/test_room_state.py -v"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pi.room_state import RoomState  # noqa: E402


def test_luc_dau_phong_trong_den_xanh():
    r = RoomState()
    assert r.occupied is False and r.led == "green"


def test_co_chuyen_dong_thi_co_nguoi_den_do():
    r = RoomState(timeout_s=300)
    assert r.update(True, 0) is True            # vừa đổi trạng thái
    assert r.occupied is True and r.led == "red"
    assert r.update(True, 1) is False           # không đổi nữa


def test_5_phut_khong_chuyen_dong_thi_phong_trong():
    r = RoomState(timeout_s=300)
    r.update(True, 0)
    assert r.update(False, 299.9) is False and r.occupied is True
    assert r.update(False, 300.0) is True and r.occupied is False
    assert r.led == "green"


def test_chuyen_dong_dat_lai_dong_ho_5_phut():
    r = RoomState(timeout_s=300)
    r.update(True, 0)
    r.update(True, 200)                          # lại thấy chuyển động lúc 200 giây
    assert r.update(False, 450) is False and r.occupied is True    # chưa đủ 5 phút từ lần cuối
    assert r.update(False, 500) is True and r.occupied is False


def test_phong_trong_roi_co_nguoi_lai_do():
    r = RoomState(timeout_s=10)
    r.update(True, 0)
    r.update(False, 20)
    assert r.occupied is False
    assert r.update(True, 21) is True and r.occupied is True


def test_phong_trong_thi_khong_chuyen_dong_van_trong():
    r = RoomState(timeout_s=10)
    for t in range(0, 100, 5):
        assert r.update(False, t) is False
    assert r.occupied is False


def test_khoi_dong_o_trang_thai_co_nguoi_roi_het_gio():
    r = RoomState(timeout_s=10, initial_occupied=True)
    assert r.update(False, 100) is False        # lần đầu: bắt đầu đếm từ đây
    assert r.update(False, 110) is True


def test_seconds_until_empty():
    r = RoomState(timeout_s=300)
    assert r.seconds_until_empty(0) is None
    r.update(True, 0)
    assert r.seconds_until_empty(100) == pytest.approx(200)
    assert r.seconds_until_empty(400) == 0


def test_timeout_khong_hop_le():
    with pytest.raises(ValueError):
        RoomState(timeout_s=0)
