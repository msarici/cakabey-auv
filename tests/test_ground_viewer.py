"""
test_ground_viewer.py — ground_viewer._print_packet malformed paket dayanıklılığı
Kara istasyonu uzun süre çalışmalı, bozuk bir paket loop'u düşürmesin.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ground_viewer


ADDR = ("127.0.0.1", 14651)


def test_print_full_valid_packet():
    pkt = {
        "seq": 5, "ts": 1234.5, "state": "TRACK",
        "detection": {"found": True, "cx": 320, "cy": 240, "area": 1500},
        "sensor": {"voltage": 14.2, "heading": 0},
        "control": {"yaw_cmd": 50, "fwd_cmd": 200},
        "fps": 28.5,
        "distance_cm": 75.3,
        "anomalies": [],
    }
    ground_viewer._print_packet(pkt, ADDR)  # raise etmemeli


def test_print_string_seq_does_not_crash():
    """seq int değil, string gelirse #{seq:6d} formatı patlamamalı."""
    pkt = {"seq": "abc", "state": "TRACK"}
    ground_viewer._print_packet(pkt, ADDR)


def test_print_missing_detection():
    pkt = {"seq": 1, "state": "SEARCH"}  # detection/sensor/control yok
    ground_viewer._print_packet(pkt, ADDR)


def test_print_none_packet():
    """JSON parse sonucu None olursa (bozuk paket)."""
    ground_viewer._print_packet(None, ADDR)


def test_print_non_dict_packet():
    """JSON liste veya string olabilir — crash etmesin."""
    ground_viewer._print_packet([1, 2, 3], ADDR)
    ground_viewer._print_packet("not a dict", ADDR)
    ground_viewer._print_packet(42, ADDR)


def test_print_packet_with_wrong_types():
    """Tüm alanlar yanlış type ile gelse de patlamasın."""
    pkt = {
        "seq": None,
        "state": 42,
        "detection": "not a dict",
        "sensor": [1, 2],
        "control": None,
        "fps": "fast",
        "distance_cm": "far",
        "anomalies": "none",
    }
    ground_viewer._print_packet(pkt, ADDR)


def test_print_packet_with_bool_voltage():
    """bool int gibi davranmamalı."""
    pkt = {"seq": 1, "state": "X", "sensor": {"voltage": True}}
    ground_viewer._print_packet(pkt, ADDR)


def test_print_packet_with_huge_seq():
    """Aşırı büyük sayı OverflowError vermemeli."""
    pkt = {"seq": 10 ** 100, "state": "X"}
    ground_viewer._print_packet(pkt, ADDR)


def test_anomalies_list_with_dicts():
    pkt = {
        "seq": 1, "state": "TRACK",
        "anomalies": [
            {"type": "algae", "bbox": [10, 20, 30, 40], "confidence": 0.5},
            {"type": "rust", "bbox": [50, 60, 70, 80], "confidence": 0.9},
        ],
    }
    ground_viewer._print_packet(pkt, ADDR)


# ---------- _process_one (loop seviyesi) ----------

def test_process_one_valid_int_seq_updates_last_seq():
    new_last, lost = ground_viewer._process_one(
        {"seq": 5, "state": "TRACK"}, ADDR, last_seq=-1, quiet=True
    )
    assert new_last == 5
    assert lost == 0


def test_process_one_detects_packet_loss():
    new_last, lost = ground_viewer._process_one(
        {"seq": 10, "state": "X"}, ADDR, last_seq=5, quiet=True
    )
    assert new_last == 10
    assert lost == 4  # seq 6,7,8,9 kayip


def test_process_one_list_packet_does_not_raise():
    """JSON [] gelirse loop crash etmemeli."""
    new_last, lost = ground_viewer._process_one([1, 2, 3], ADDR, last_seq=5, quiet=True)
    assert new_last == 5  # değişmemiş
    assert lost == 0


def test_process_one_none_packet_does_not_raise():
    """JSON null gelirse loop crash etmemeli."""
    new_last, lost = ground_viewer._process_one(None, ADDR, last_seq=5, quiet=True)
    assert new_last == 5
    assert lost == 0


def test_process_one_string_seq_does_not_raise():
    """{'seq': 'abc'} → seq > last_seq + 1 TypeError olmamalı."""
    new_last, lost = ground_viewer._process_one(
        {"seq": "abc", "state": "X"}, ADDR, last_seq=5, quiet=True
    )
    assert new_last == 5  # last_seq korundu
    assert lost == 0


def test_process_one_float_seq_does_not_raise():
    new_last, lost = ground_viewer._process_one(
        {"seq": 3.14}, ADDR, last_seq=5, quiet=True
    )
    assert new_last == 5
    assert lost == 0


def test_process_one_bool_seq_does_not_count():
    """bool int subclass'ı; True=1 olarak yorumlanmasın."""
    new_last, lost = ground_viewer._process_one(
        {"seq": True}, ADDR, last_seq=5, quiet=True
    )
    assert new_last == 5
    assert lost == 0


def test_process_one_missing_seq_uses_default():
    """seq alanı yoksa default -1 → last_seq>=0 değil → loss hesabı atlanır."""
    new_last, lost = ground_viewer._process_one(
        {"state": "X"}, ADDR, last_seq=5, quiet=True
    )
    # default -1 int, izin verilen path → loss=0, last_seq=-1 olarak güncellenir
    assert new_last == -1
    assert lost == 0


def test_process_one_scalar_packet_does_not_raise():
    """JSON sayı/string/bool gelirse crash etmesin."""
    for bad in (42, "raw", True):
        new_last, lost = ground_viewer._process_one(bad, ADDR, last_seq=10, quiet=True)
        assert new_last == 10
        assert lost == 0
