"""
test_video_sender.py — MJPEG-UDP video sender testleri (loopback)
"""

import os
import socket
import struct
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from video_sender import VideoSender, HEADER, HEADER_SIZE, MAX_CHUNK_PAYLOAD


def _make_receiver(port, bufsize=1 << 20):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, bufsize)
    except OSError:
        pass
    sock.bind(("127.0.0.1", port))
    sock.settimeout(1.5)
    return sock


def _drain_one_frame(rx):
    """Tek bir frame'in tum chunk'larini topla, JPEG bytes dondur."""
    chunks = {}
    total = None
    fid_seen = None
    while True:
        data, _addr = rx.recvfrom(65535)
        if len(data) < HEADER_SIZE:
            continue
        fid, cid, t = HEADER.unpack(data[:HEADER_SIZE])
        if fid_seen is None:
            fid_seen = fid
        elif fid != fid_seen:
            # Yeni frame baslamis, eski tamamlanmadi
            continue
        if total is None:
            total = t
        chunks[cid] = data[HEADER_SIZE:]
        if len(chunks) == total:
            return b"".join(chunks[i] for i in range(total)), fid_seen


def _dummy_frame(w=320, h=240):
    return np.full((h, w, 3), 64, dtype=np.uint8)


def test_disabled_does_not_open_socket():
    vs = VideoSender(host="127.0.0.1", port=0, enabled=False)
    assert vs._sock is None
    assert vs.send(_dummy_frame()) is False
    vs.close()


def test_send_none_frame_returns_false():
    vs = VideoSender(host="127.0.0.1", port=14861, send_interval_s=0.0)
    try:
        assert vs.send(None) is False
    finally:
        vs.close()


def test_send_small_frame_single_chunk():
    port = 14861
    rx = _make_receiver(port)
    try:
        vs = VideoSender(host="127.0.0.1", port=port, send_interval_s=0.0,
                         max_width=320)
        ok = vs.send(_dummy_frame())
        assert ok is True

        data, _addr = rx.recvfrom(65535)
        assert len(data) > HEADER_SIZE
        fid, cid, total = HEADER.unpack(data[:HEADER_SIZE])
        assert fid == 0
        assert cid == 0
        # 320x240 boş bir karenin JPEG'i tek chunk'a sığar
        assert total == 1

        vs.close()
    finally:
        rx.close()


def test_frame_id_increments():
    port = 14862
    rx = _make_receiver(port)
    try:
        vs = VideoSender(host="127.0.0.1", port=port, send_interval_s=0.0,
                         max_width=320)
        seen_ids = []
        for _ in range(3):
            vs.send(_dummy_frame())
            jpg, fid = _drain_one_frame(rx)
            seen_ids.append(fid)
            assert len(jpg) > 0  # JPEG bytes geldi
        assert seen_ids == [0, 1, 2]
        vs.close()
    finally:
        rx.close()


def test_rate_limit_drops_fast_sends():
    port = 14863
    rx = _make_receiver(port)
    try:
        vs = VideoSender(host="127.0.0.1", port=port, send_interval_s=0.5,
                         max_width=320)
        results = [vs.send(_dummy_frame()) for _ in range(5)]
        assert results.count(True) == 1
        assert results.count(False) == 4
        assert vs.stats()["dropped_rate"] == 4
        vs.close()
    finally:
        rx.close()


def test_downscale_when_too_wide():
    """max_width'ten genis frame downscale edilmeli."""
    port = 14864
    rx = _make_receiver(port)
    try:
        vs = VideoSender(host="127.0.0.1", port=port, send_interval_s=0.0,
                         max_width=320, jpeg_quality=60)
        big = _dummy_frame(w=1280, h=720)
        ok = vs.send(big)
        assert ok is True
        # JPEG'i geri al, decode et, en/boy oranını koruyarak 320'e inmis mi?
        import cv2
        jpg, _ = _drain_one_frame(rx)
        img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert img is not None
        assert img.shape[1] == 320
        # 1280:720 = 16:9 -> 320'de y=180
        assert img.shape[0] == 180
        vs.close()
    finally:
        rx.close()


def test_send_does_not_raise_on_unreachable():
    """Network down: send asla raise etmemeli."""
    vs = VideoSender(host="240.0.0.1", port=1, send_interval_s=0.0)
    try:
        result = vs.send(_dummy_frame())
        assert result in (True, False)
    finally:
        vs.close()


def test_close_is_idempotent():
    vs = VideoSender(host="127.0.0.1", port=14865, enabled=False)
    vs.close()
    vs.close()
