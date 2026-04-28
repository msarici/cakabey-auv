"""
test_ground_station.py — UDP telemetri sender testleri (loopback)
"""

import sys
import os
import json
import socket
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ground_station import GroundStation


def _make_receiver(port):
    """Loopback'te UDP dinleyici socket aç."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.settimeout(1.0)
    return sock


def test_disabled_does_not_open_socket():
    gs = GroundStation(host="127.0.0.1", port=0, enabled=False)
    assert gs._sock is None
    assert gs.send({"x": 1}) is False
    gs.close()


def test_send_loopback_packet_received():
    port = 14751
    rx = _make_receiver(port)
    try:
        gs = GroundStation(host="127.0.0.1", port=port, send_interval_s=0.0)
        ok = gs.send({"state": "TRACK", "detection": {"found": True, "cx": 320}})
        assert ok is True

        data, _addr = rx.recvfrom(65535)
        pkt = json.loads(data.decode("utf-8"))
        assert pkt["state"] == "TRACK"
        assert pkt["detection"]["found"] is True
        assert pkt["detection"]["cx"] == 320
        assert "seq" in pkt
        assert "ts" in pkt
        gs.close()
    finally:
        rx.close()


def test_seq_increments():
    """
    Send/recv interleaved (Windows loopback'te bursty UDP düşüyor —
    üretimde rate limit var, gerçekçi davranış lockstep).
    """
    port = 14752
    rx = _make_receiver(port)
    try:
        gs = GroundStation(host="127.0.0.1", port=port, send_interval_s=0.0)
        seqs = []
        for _ in range(3):
            gs.send({"x": 1})
            data, _ = rx.recvfrom(65535)
            seqs.append(json.loads(data.decode("utf-8"))["seq"])
        assert seqs == [0, 1, 2]
        gs.close()
    finally:
        rx.close()


def test_rate_limit_drops_fast_sends():
    port = 14753
    rx = _make_receiver(port)
    try:
        gs = GroundStation(host="127.0.0.1", port=port, send_interval_s=0.5)
        # Hızlı arka arkaya 5 send: sadece 1'i gitmeli
        results = [gs.send({"i": i}) for i in range(5)]
        assert results.count(True) == 1
        assert results.count(False) == 4
        assert gs.stats()["dropped_rate"] == 4
        gs.close()
    finally:
        rx.close()


def test_rate_limit_respects_interval():
    port = 14754
    rx = _make_receiver(port)
    try:
        gs = GroundStation(host="127.0.0.1", port=port, send_interval_s=0.05)
        gs.send({"i": 0})
        time.sleep(0.07)
        ok = gs.send({"i": 1})
        assert ok is True
        gs.close()
    finally:
        rx.close()


def test_send_does_not_raise_on_unreachable_host():
    """Network down case: send() asla raise etmemeli."""
    # 240.0.0.0/4 reserved, çoğu sistemde hata verir veya sessiz drop edilir
    gs = GroundStation(host="240.0.0.1", port=1, send_interval_s=0.0)
    try:
        # send hata yutmali
        result = gs.send({"x": 1})
        # True veya False olabilir, OS'a bagli — kritik olan raise etmemesi
        assert result in (True, False)
    finally:
        gs.close()


def test_close_is_idempotent():
    gs = GroundStation(host="127.0.0.1", port=14755, enabled=False)
    gs.close()
    gs.close()  # ikinci close hata vermemeli


def test_payload_with_none_values_serializes():
    """distance_cm None olabilir — JSON null'a serialize olmali."""
    port = 14756
    rx = _make_receiver(port)
    try:
        gs = GroundStation(host="127.0.0.1", port=port, send_interval_s=0.0)
        gs.send({"distance_cm": None, "anomalies": []})
        data, _ = rx.recvfrom(65535)
        pkt = json.loads(data.decode("utf-8"))
        assert pkt["distance_cm"] is None
        assert pkt["anomalies"] == []
        gs.close()
    finally:
        rx.close()
