"""
test_command_link.py — UDP komut sender/receiver testleri (loopback)
"""

import json
import os
import socket
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command_link import CommandSender, CommandReceiver, _clamp


def test_clamp_basic():
    assert _clamp(0.5) == 0.5
    assert _clamp(-2.0) == -1.0
    assert _clamp(2.0) == 1.0
    assert _clamp(None) == 0.0
    assert _clamp("abc") == 0.0
    assert _clamp(float("nan")) == 0.0


def test_sender_disabled_no_socket():
    s = CommandSender(host="127.0.0.1", port=0, enabled=False)
    assert s._sock is None
    assert s.send({"fwd": 0.5}) is False
    s.close()


def test_loopback_round_trip():
    port = 14953
    rx = CommandReceiver(bind="127.0.0.1", port=port, stale_after_s=10.0)
    tx = CommandSender(host="127.0.0.1", port=port, send_interval_s=0.0)
    try:
        tx.send({"fwd": 0.7, "yaw": -0.4, "vertical": 0.2,
                 "emergency_stop": False}, mode="manual")
        # Pakete kuyrukta yer bulmasi icin kucuk bekleme
        time.sleep(0.05)
        rx.poll()
        cmd, stale = rx.get_command()
        assert stale is False
        assert cmd["mode"] == "manual"
        assert abs(cmd["fwd"] - 0.7) < 1e-6
        assert abs(cmd["yaw"] - (-0.4)) < 1e-6
        assert cmd["emergency_stop"] is False
    finally:
        tx.close()
        rx.close()


def test_receiver_stale_default_when_no_packet():
    port = 14954
    rx = CommandReceiver(bind="127.0.0.1", port=port, stale_after_s=0.01)
    try:
        cmd, stale = rx.get_command()
        # Hic paket gelmemis: stale True OR safe-default mode (auto, sifir).
        # Burada last_cmd None oldugu icin stale flag False ama safe.
        assert cmd["fwd"] == 0.0
        assert cmd["yaw"] == 0.0
        assert cmd["mode"] == "auto"
    finally:
        rx.close()


def test_receiver_stale_after_old_packet():
    port = 14955
    rx = CommandReceiver(bind="127.0.0.1", port=port, stale_after_s=0.05)
    tx = CommandSender(host="127.0.0.1", port=port, send_interval_s=0.0)
    try:
        tx.send({"fwd": 0.5}, mode="manual")
        time.sleep(0.05)
        rx.poll()
        # Hemen oku — fresh
        cmd, stale = rx.get_command()
        assert stale is False
        # Eskimesini bekle
        time.sleep(0.1)
        cmd, stale = rx.get_command()
        assert stale is True
        assert cmd["mode"] == "auto"   # stale -> auto'ya don
        assert cmd["fwd"] == 0.0
        assert cmd["yaw"] == 0.0
    finally:
        tx.close()
        rx.close()


def test_receiver_keeps_latest_packet():
    """Birden cok paket geldiyse get_command sonuncuyu vermeli.

    Windows loopback bursty UDP'yi dusurmeye meyilli (ground_station
    testlerinde de benzer not var). Lockstep send/poll yaparak garanti
    edelim — uretimde sender 50Hz'le yayar, alici loop her frame poll'lar."""
    port = 14956
    rx = CommandReceiver(bind="127.0.0.1", port=port, stale_after_s=10.0)
    tx = CommandSender(host="127.0.0.1", port=port, send_interval_s=0.0)
    try:
        for fwd_v in [0.1, 0.2, 0.3]:
            tx.send({"fwd": fwd_v}, mode="manual")
            time.sleep(0.02)
            rx.poll()
        cmd, _ = rx.get_command()
        assert abs(cmd["fwd"] - 0.3) < 1e-6
    finally:
        tx.close()
        rx.close()


def test_sender_clamps_values():
    """-2 -> -1, 2 -> 1 olmali, hat icinde."""
    port = 14957
    rx = CommandReceiver(bind="127.0.0.1", port=port, stale_after_s=10.0)
    tx = CommandSender(host="127.0.0.1", port=port, send_interval_s=0.0)
    try:
        tx.send({"fwd": 5.0, "yaw": -9.9}, mode="manual")
        time.sleep(0.05)
        rx.poll()
        cmd, _ = rx.get_command()
        assert cmd["fwd"] == 1.0
        assert cmd["yaw"] == -1.0
    finally:
        tx.close()
        rx.close()


def test_receiver_rejects_malformed_packet():
    """Bozuk JSON / dict olmayan paket: parse_errors artar, crash etmez.

    Windows loopback'te bursty UDP drop'unu onlemek icin paketleri
    araliklayarak gonder + her birinden sonra poll.
    """
    port = 14958
    rx = CommandReceiver(bind="127.0.0.1", port=port, stale_after_s=10.0)
    raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for pkt in (b"not-json", b"[1,2,3]"):
            raw.sendto(pkt, ("127.0.0.1", port))
            time.sleep(0.02)
            rx.poll()
        assert rx.stats()["parse_errors"] >= 2
        cmd, _ = rx.get_command()
        # Bu paketler tutulmamali; safe default donmeli
        assert cmd["mode"] == "auto"
    finally:
        raw.close()
        rx.close()


def test_sender_does_not_raise_on_unreachable():
    tx = CommandSender(host="240.0.0.1", port=1, send_interval_s=0.0)
    try:
        result = tx.send({"fwd": 0.5}, mode="manual")
        assert result in (True, False)
    finally:
        tx.close()


def test_close_is_idempotent():
    rx = CommandReceiver(bind="127.0.0.1", port=14959, stale_after_s=1.0)
    rx.close()
    rx.close()

    tx = CommandSender(host="127.0.0.1", port=14959, enabled=False)
    tx.close()
    tx.close()
