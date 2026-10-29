"""Bounded packet handling and restart/reordering tests; no pygame required."""
from unittest.mock import Mock
import cv2
import numpy as np
import pytest
import video_viewer as viewer


@pytest.fixture
def receiver(monkeypatch):
    sock = Mock()
    monkeypatch.setattr(viewer.socket, 'socket', Mock(return_value=sock))
    rx = viewer.FrameReceiver(bind='127.0.0.1', source_host='192.168.2.2', allow_insecure=True)
    return rx


def packet(fid=1, cid=0, total=1, payload=b'bad'):
    return viewer.HEADER.pack(fid, cid, total) + payload, ('192.168.2.2', 12345)


def jpeg():
    ok, data = cv2.imencode('.jpg', np.zeros((20, 30, 3), dtype=np.uint8))
    assert ok
    return data.tobytes()


def feed(rx, packets):
    rx._sock.recvfrom.side_effect = list(packets) + [BlockingIOError]
    return rx.poll()


def test_normal_chunked_jpeg(receiver):
    data = jpeg()
    mid = len(data) // 2
    result = feed(receiver, [packet(cid=1, total=2, payload=data[mid:]),
                             packet(cid=0, total=2, payload=data[:mid])])
    assert result.shape == (20, 30, 3)
    assert receiver.stats()['frames_decoded'] == 1


@pytest.mark.parametrize('cid,total', [(0, 0), (4, 4), (0, 65535)])
def test_invalid_chunk_headers_rejected(receiver, cid, total):
    assert feed(receiver, [packet(cid=cid, total=total)]) is None
    assert not receiver._partial


def test_partial_frame_count_is_bounded(receiver):
    feed(receiver, [packet(fid=i, total=2) for i in range(20)])
    assert len(receiver._partial) == viewer.REASSEMBLY_BUFFER
    assert receiver.stats()['frames_dropped'] == 16


def test_poll_has_packet_budget_under_continuous_traffic(receiver):
    receiver._sock.recvfrom.side_effect = None
    receiver._sock.recvfrom.return_value = packet(total=2)
    assert receiver.poll() is None
    assert receiver._sock.recvfrom.call_count == viewer.MAX_PACKETS_PER_POLL


def test_unexpected_source_rejected(receiver):
    p, _ = packet(payload=jpeg())
    assert feed(receiver, [(p, ('192.168.2.99', 1))]) is None
    assert not receiver._partial


def test_duplicate_completed_frame_not_decoded_again(receiver):
    data = jpeg()
    assert feed(receiver, [packet(fid=10, payload=data)]) is not None
    assert feed(receiver, [packet(fid=9, payload=data), packet(fid=10, payload=data)]) is None
    assert receiver.stats()['frames_decoded'] == 1


def test_sender_restart_allowed_after_idle(receiver, monkeypatch):
    data = jpeg()
    assert feed(receiver, [packet(fid=1000, payload=data)]) is not None
    monkeypatch.setattr(viewer.time, 'monotonic', lambda: receiver._last_complete_t + 2)
    assert feed(receiver, [packet(fid=0, payload=data)]) is not None


def test_frame_id_wraparound(receiver):
    data = jpeg()
    assert feed(receiver, [packet(fid=0xFFFFFFFF, payload=data)]) is not None
    assert feed(receiver, [packet(fid=0, payload=data)]) is not None


def test_jpeg_dimension_bomb_rejected_before_decode(receiver, monkeypatch):
    # SOF0 segment advertising 65535 x 65535 pixels.
    bomb = b'\xff\xd8\xff\xc0\x00\x08\x08\xff\xff\xff\xff\x00'
    decode = Mock(side_effect=AssertionError('decoder must not be called'))
    monkeypatch.setattr(viewer.cv2, 'imdecode', decode)
    assert feed(receiver, [packet(payload=bomb)]) is None
    decode.assert_not_called()
    assert receiver.stats()['decode_errors'] == 1


def test_chunk_size_bound(receiver):
    assert feed(receiver, [packet(payload=b'x' * (viewer.MAX_CHUNK_BYTES + 1))]) is None
    assert not receiver._partial


def test_decode_work_is_bounded_per_poll(receiver):
    data = jpeg()
    result = feed(receiver, [packet(fid=i, payload=data) for i in range(20)])
    assert result is not None
    assert receiver.stats()['frames_decoded'] == viewer.MAX_DECODES_PER_POLL
    assert receiver._sock.recvfrom.call_count == viewer.MAX_DECODES_PER_POLL
