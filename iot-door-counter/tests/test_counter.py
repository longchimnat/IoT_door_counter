"""Kiểm thử thuật toán đếm (pi/counter.py) trên dữ liệu giả - không cần phần cứng.

Chạy:  python -m pytest tests/test_counter.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pi.counter import BLOCKED, CALIBRATING, IDLE, Counter  # noqa: E402

DT = 0.05   # 20 mẫu mỗi giây


def feed(c, segments, t=0.0):
    """segments = [(giá trị cm, số mẫu), ...]. Trả về (danh sách thời điểm đếm được, t kế tiếp)."""
    counted = []
    for value, n in segments:
        for _ in range(n):
            if c.update(value, t):
                counted.append(round(t, 2))
            t += DT
    return counted, t


def ready(**kw):
    c = Counter(**kw)
    _, t = feed(c, [(150, 20)])
    return c, t


def test_hieu_chuan_nen_truoc_khi_dem():
    c = Counter()
    feed(c, [(150, 14)])
    assert c.state == CALIBRATING and c.baseline is None
    feed(c, [(150, 1)])
    assert c.state == IDLE and c.baseline == pytest.approx(150)


def test_nen_la_trung_vi_nen_chiu_duoc_nhieu_luc_khoi_dong():
    c = Counter()
    feed(c, [(150, 7), (60, 2), (150, 6)])      # có người đi qua lúc hiệu chuẩn
    assert c.baseline == pytest.approx(150)
    assert c.count == 0


def test_mot_luot_di_qua_dem_1():
    c, t = ready()
    counted, _ = feed(c, [(60, 6), (150, 10)], t)
    assert c.count == 1 and len(counted) == 1


def test_dem_tai_luc_tra_lai_khong_phai_luc_chan():
    c, t = ready()
    counted, _ = feed(c, [(60, 6)], t)
    assert counted == [] and c.state == BLOCKED
    counted, _ = feed(c, [(150, 3)], t + 6 * DT)
    assert len(counted) == 1


def test_hai_lan_chan_cach_duoi_1_giay_chi_tinh_1():
    c, t = ready()
    feed(c, [(60, 5), (150, 10), (60, 5), (150, 10)], t)      # cách nhau 0,5 giây
    assert c.count == 1


def test_hai_lan_chan_cach_tren_1_giay_tinh_2():
    c, t = ready()
    feed(c, [(60, 5), (150, 25), (60, 5), (150, 10)], t)      # cách nhau 1,25 giây
    assert c.count == 2


def test_chuoi_chan_lien_tiep_trong_1_giay_van_chi_1():
    c, t = ready()
    feed(c, [(60, 4), (150, 6), (60, 4), (150, 6), (60, 4), (150, 10)], t)
    assert c.count == 1


def test_min_gap_cau_hinh_duoc():
    c, t = ready(min_gap_s=0.2)
    feed(c, [(60, 5), (150, 10), (60, 5), (150, 10)], t)      # cách 0,5 giây > 0,2
    assert c.count == 2


def test_mau_nhieu_le_khong_gay_dem_sai():
    c, t = ready()
    feed(c, [(60, 1), (150, 10), (60, 1), (150, 10)], t)
    assert c.count == 0


def test_mau_nhieu_le_trong_luc_dang_chan_khong_ket_thuc_som():
    c, t = ready()
    feed(c, [(60, 5), (150, 1), (60, 5), (150, 10)], t)      # một mẫu nhảy lên giữa chừng
    assert c.count == 1


def test_chay_nhanh_chan_rat_ngan_van_dem():
    c, t = ready()
    feed(c, [(60, 2), (150, 10)], t)                          # 0,1 giây
    assert c.count == 1


def test_dung_chan_cua_3_giay_roi_di_dem_1():
    c, t = ready()
    counted, _ = feed(c, [(60, 60), (150, 10)], t)
    assert c.count == 1 and len(counted) == 1


def test_vung_dem_giua_hai_nguong_khong_ket_thuc_luot():
    c, t = ready()
    feed(c, [(60, 5), (120, 5), (60, 5), (150, 10)], t)       # 120 nằm giữa 105 và 127,5
    assert c.count == 1


def test_nguong_drop_ratio():
    c, t = ready()
    feed(c, [(110, 10), (150, 10)], t)                        # 110 > 0,7 x 150 = 105
    assert c.count == 0
    feed(c, [(100, 10), (150, 10)], t + 1.0)                  # 100 < 105
    assert c.count == 1


def test_vat_dung_yen_qua_lau_khong_dem_va_hoc_lai_nen():
    c, t = ready()
    counted, t = feed(c, [(60, 200)], t)                      # 10 giây > 8 giây
    assert counted == [] and c.count == 0
    assert c.baseline == pytest.approx(60)                    # đã học nền mới
    counted, t = feed(c, [(150, 20)], t)                      # vật bị bỏ đi
    assert counted == [] and c.baseline == pytest.approx(150)
    feed(c, [(60, 6), (150, 10)], t)
    assert c.count == 1                                       # vẫn đếm tiếp bình thường


def test_nen_xa_hon_lien_tuc_thi_doi_nen_nhanh():
    c, t = ready()
    _, t = feed(c, [(200, 15)], t)                            # mở cửa, không còn tường
    assert c.baseline == pytest.approx(200)
    feed(c, [(130, 6), (200, 10)], t)                         # 130 < 0,7 x 200 = 140
    assert c.count == 1


def test_nen_troi_cham_khong_gay_dem_va_nen_theo_kip():
    c, t = ready()
    drift = [(150 - i * 0.1, 1) for i in range(200)]          # 150 -> 130 trong 10 giây
    counted, t = feed(c, drift, t)
    assert counted == [] and c.baseline < 145
    feed(c, [(60, 6), (c.baseline, 10)], t)
    assert c.count == 1


def test_mau_khong_hop_le_bi_bo_qua():
    c, t = ready()
    feed(c, [(60, 5), (None, 3), (0, 3), (60, 2), (150, 10)], t)
    assert c.count == 1


def test_gia_tri_lon_hon_toi_da_bi_cat():
    c = Counter(max_cm=200)
    feed(c, [(999, 15)])
    assert c.baseline == pytest.approx(200)


def test_reset_ve_0_giu_nguyen_nen():
    c, t = ready()
    feed(c, [(60, 5), (150, 10)], t)
    assert c.count == 1
    c.reset()
    assert c.count == 0 and c.baseline == pytest.approx(150) and c.state == IDLE


def test_recalibrate_giu_nguyen_so_luot():
    c, t = ready()
    feed(c, [(60, 5), (150, 10)], t)
    c.recalibrate()
    assert c.count == 1 and c.state == CALIBRATING


def test_update_tra_ve_true_dung_mot_lan_moi_luot():
    c, t = ready()
    flags = []
    for v in [60] * 5 + [150] * 10:
        flags.append(c.update(v, t))
        t += DT
    assert flags.count(True) == 1


def test_dung_dong_ho_he_thong_neu_khong_truyen_t():
    c = Counter(baseline_samples=3)
    for _ in range(3):
        c.update(150)
    assert c.state == IDLE


@pytest.mark.parametrize("kw", [
    {"drop_ratio": 0.9, "return_ratio": 0.8},
    {"drop_ratio": 0.0},
    {"return_ratio": 1.5},
    {"far_ratio": 1.0},
    {"debounce": 0},
    {"baseline_alpha": 0},
    {"max_block_s": 0},
    {"min_gap_s": -1},
])
def test_tham_so_sai_bi_tu_choi(kw):
    with pytest.raises(ValueError):
        Counter(**kw)
