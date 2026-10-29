"""Authenticated telemetry and video regression tests."""
import json
import socket
from unittest.mock import Mock
import cv2
import numpy as np
import pytest
import telemetry_auth as authmod
from telemetry_auth import DatagramAuthenticator
from ground_station import GroundStation
from ground_viewer import decode_packet, _process_one
from video_sender import VideoSender
from video_viewer import FrameReceiver, HEADER

KEY = b'test-only-stream-key-' * 3


def pair(channel='telemetry', window=0):
    return (DatagramAuthenticator(channel, auth_key=KEY),
            DatagramAuthenticator(channel, auth_key=KEY, reorder_window=window))


@pytest.mark.parametrize('factory', [GroundStation, VideoSender, FrameReceiver])
def test_missing_key_fails_closed(monkeypatch, factory):
    monkeypatch.delenv('CAKABEY_COMMAND_KEY', raising=False)
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize('factory,kwargs', [(GroundStation, {'host':'192.168.2.1'}),
    (VideoSender, {'host':'192.168.2.1'}), (FrameReceiver, {'bind':'0.0.0.0'})])
def test_insecure_stream_is_loopback_only(factory, kwargs):
    with pytest.raises(ValueError):
        factory(allow_insecure=True, **kwargs)


def test_authentication_and_channel_separation():
    tx, rx = pair()
    wire = tx.encode(b'payload')
    for bad in (b'unsigned', wire[:-1] + bytes([wire[-1] ^ 1])):
        with pytest.raises(ValueError):
            rx.decode(bad)
    wrong = DatagramAuthenticator('telemetry', auth_key=b'wrong-secret-'*4)
    with pytest.raises(ValueError):
        wrong.decode(wire)
    video = DatagramAuthenticator('video', auth_key=KEY)
    with pytest.raises(ValueError):
        video.decode(wire)
    assert rx.decode(wire) == b'payload'


def test_duplicates_reordering_and_session_change_rejected():
    tx, rx = pair()
    first, second = tx.encode(b'first'), tx.encode(b'second')
    assert rx.decode(second) == b'second'
    for old in (first, second):
        with pytest.raises(ValueError):
            rx.decode(old)
    fresh_sender = DatagramAuthenticator('telemetry', auth_key=KEY)
    with pytest.raises(ValueError):
        rx.decode(fresh_sender.encode(b'new-session'))


def test_video_reordering_window_bounded():
    tx, rx = pair('video', window=4)
    wires = [tx.encode(str(i).encode()) for i in range(8)]
    assert rx.decode(wires[3]) == b'3'
    assert rx.decode(wires[1]) == b'1'
    with pytest.raises(ValueError):
        rx.decode(wires[1])
    assert rx.decode(wires[7]) == b'7'
    with pytest.raises(ValueError):
        rx.decode(wires[2])
    assert len(rx._seen) <= 5


def test_stale_and_future_wire_rejected(monkeypatch):
    tx, rx = pair()
    monkeypatch.setattr(authmod.time, 'time', lambda: 100)
    wire = tx.encode(b'payload')
    for now in (103, 99):
        monkeypatch.setattr(authmod.time, 'time', lambda: now)
        with pytest.raises(ValueError):
            rx.decode(wire)


def test_telemetry_real_socket_round_trip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0)); sock.settimeout(1)
    tx = GroundStation(host='127.0.0.1', port=sock.getsockname()[1], auth_key=KEY)
    rx = DatagramAuthenticator('telemetry', auth_key=KEY)
    try:
        assert tx.send({'seq': 999, 'ts': -1, 'state': 'TRACK', 'sensor': {'voltage': 14}})
        wire, _ = sock.recvfrom(65535)
        pkt = decode_packet(wire, rx)
        assert pkt['seq'] == 0  # caller cannot overwrite transport sequence
        assert pkt['ts'] > 0
        assert pkt['sensor']['voltage'] == 14
    finally:
        tx.close(); sock.close()


@pytest.mark.parametrize('payload', [b'[]', b'{"seq":0,"ts":1,"sensor":[]}',
    b'{"seq":true,"ts":1}', b'{"seq":0,"ts":1,"x":NaN}',
    b'{"seq":0,"ts":1,"x":1e999}', b'{"seq":0,"seq":1,"ts":1}'])
def test_authenticated_invalid_json_rejected(payload):
    tx, rx = pair()
    with pytest.raises((ValueError, TypeError)):
        decode_packet(tx.encode(payload), rx)


def test_old_seq_does_not_rewind_loss_counter():
    last, loss = _process_one({'seq': 10}, None, 5, quiet=True)
    assert (last, loss) == (10, 4)
    assert _process_one({'seq': 6}, None, last, quiet=True) == (10, 0)
    assert _process_one({'seq': 11}, None, last, quiet=True) == (11, 0)


def test_secure_video_roundtrip_and_unsigned_rejection():
    rx = FrameReceiver(bind='127.0.0.1', port=0, auth_key=KEY)
    tx = VideoSender(host='127.0.0.1', port=rx._sock.getsockname()[1], auth_key=KEY,
                     send_interval_s=0)
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    try:
        assert tx.send(image)
        assert rx.poll().shape == image.shape
        ok, jpeg = cv2.imencode('.jpg', image)
        assert ok
        tx._sock.sendto(HEADER.pack(2,0,1)+jpeg.tobytes(),('127.0.0.1',rx._sock.getsockname()[1]))
        assert rx.poll() is None
        assert rx.stats()['auth_errors'] == 1
    finally:
        tx.close(); rx.close()


def test_video_replay_rejected_before_decode(monkeypatch):
    rx = FrameReceiver(bind='127.0.0.1', port=0, auth_key=KEY)
    tx = DatagramAuthenticator('video', auth_key=KEY)
    ok, jpeg = cv2.imencode('.jpg', np.zeros((20,30,3),dtype=np.uint8))
    assert ok
    wire = tx.encode(HEADER.pack(0,0,1)+jpeg.tobytes())
    rx._sock.close()
    rx._sock = Mock()
    rx._sock.recvfrom.side_effect = [(wire,('127.0.0.1',1)),BlockingIOError]
    assert rx.poll() is not None
    decoder = Mock(side_effect=AssertionError('Replay must not decode'))
    monkeypatch.setattr(cv2,'imdecode',decoder)
    rx._sock.recvfrom.side_effect = [(wire,('127.0.0.1',1)),BlockingIOError]
    assert rx.poll() is None
    decoder.assert_not_called()
    rx.close()


def test_partial_video_send_never_reuses_frame_id(monkeypatch):
    import video_sender
    monkeypatch.setattr(video_sender, 'MAX_CHUNK_PAYLOAD', 100)
    tx = VideoSender(host='127.0.0.1', port=1, allow_insecure=True, send_interval_s=0)
    tx._sock.close()
    sock = Mock()
    tx._sock = sock
    sock.sendto.side_effect = [100, OSError('queue full')]
    image = np.zeros((20,30,3),dtype=np.uint8)
    assert not tx.send(image)
    assert HEADER.unpack(sock.sendto.call_args_list[0].args[0][:8])[0] == 0
    sock.reset_mock()
    sock.sendto.side_effect = None
    assert tx.send(image)
    assert all(HEADER.unpack(call.args[0][:8])[0] == 1 for call in sock.sendto.call_args_list)
    tx.close()


def test_telemetry_nan_and_oversize_do_not_escape():
    tx = GroundStation(host='127.0.0.1', port=1, auth_key=KEY, send_interval_s=0)
    try:
        assert not tx.send({'voltage': float('nan')})
        assert not tx.send({'large': 'x'*65507})
        assert tx.stats()['send_errors'] == 2
    finally:
        tx.close()
