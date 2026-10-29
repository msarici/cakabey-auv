"""Authentication, freshness and bounded-work regressions with loopback UDP."""
import json
import socket
import time
from unittest.mock import Mock
import pytest
import command_link as link

KEY = b'test-only-secret-' * 4


@pytest.fixture
def pair():
    rx = link.CommandReceiver(bind='127.0.0.1', port=0, auth_key=KEY)
    tx = link.CommandSender(host='127.0.0.1', port=rx._sock.getsockname()[1],
                            send_interval_s=0, auth_key=KEY)
    tx.send({})
    rx.poll()
    tx._handshake(time.monotonic())
    assert tx._nonce is not None
    yield tx, rx
    tx.close()
    rx.close()


def packet(tx, seq=0, **changes):
    pkt = dict(kind='command', session=tx._session, nonce=tx._nonce,
               seq=seq, ts=time.monotonic(), mode='manual', fwd=.5, yaw=0.,
               vertical=0., emergency_stop=False)
    pkt.update(changes)
    return pkt


def inject(tx, rx, data):
    tx._sock.sendto(data, ('127.0.0.1', rx._sock.getsockname()[1]))
    rx.poll()


@pytest.mark.parametrize('klass', [link.CommandSender, link.CommandReceiver])
def test_missing_and_short_key_fail_closed(monkeypatch, klass):
    monkeypatch.delenv('CAKABEY_COMMAND_KEY', raising=False)
    with pytest.raises(ValueError):
        klass()
    with pytest.raises(ValueError):
        klass(auth_key='short')
    disabled = klass(enabled=False)
    assert disabled._sock is None


def test_unsigned_wrong_key_and_tampering_do_not_refresh_command(pair):
    tx, rx = pair
    for data in (json.dumps(packet(tx)).encode(), link._encode(packet(tx), b'wrong' * 10)):
        inject(tx, rx, data)
    signed = json.loads(link._encode(packet(tx), KEY))
    signed['fwd'] = 1
    inject(tx, rx, json.dumps(signed).encode())
    assert rx._last_cmd_t is None
    assert rx.stats()['recv_count'] == 0


def test_duplicate_and_out_of_order_do_not_refresh_freshness(pair):
    tx, rx = pair
    inject(tx, rx, link._encode(packet(tx, seq=2), KEY))
    last = rx._last_cmd_t
    for seq in [2, 1, 0]:
        inject(tx, rx, link._encode(packet(tx, seq=seq, fwd=1), KEY))
    assert rx._last_cmd_t == last
    assert rx.get_command()[0]['fwd'] == .5
    assert rx.stats()['recv_count'] == 1


def test_receiver_restart_rejects_captured_commands(pair):
    tx, rx = pair
    captured = link._encode(packet(tx), KEY)
    replacement = link.CommandReceiver(bind='127.0.0.1', port=0, auth_key=KEY)
    try:
        inject(tx, replacement, captured)
        assert replacement._last_cmd_t is None
    finally:
        replacement.close()


def test_nonce_lease_expires_without_any_shared_clock(pair):
    tx, rx = pair
    rx._nonce_t = time.monotonic() - link.NONCE_LEASE_S - 1
    inject(tx, rx, link._encode(packet(tx), KEY))
    assert rx._last_cmd_t is None


def test_old_nonce_rejected_after_renewal(pair):
    tx, rx = pair
    old = link._encode(packet(tx), KEY)
    tx._last_hello = float('-inf')
    tx._handshake(time.monotonic())
    rx.poll()
    inject(tx, rx, old)
    assert rx._last_cmd_t is None
    tx._handshake(time.monotonic())
    assert tx.send({'fwd': .4})
    rx.poll()
    assert rx.get_command()[0]['fwd'] == .4


def test_replayed_hello_does_not_invalidate_current_nonce(pair):
    tx, rx = pair
    before = rx._nonce
    hello = {'kind': 'hello', 'session': tx._session,
             'request': 'a' * 32, 'hello_seq': 0}
    inject(tx, rx, link._encode(hello, KEY))
    assert rx._nonce == before


@pytest.mark.parametrize('changes', [dict(seq=True), dict(seq=-1), dict(seq='1'),
    dict(fwd=float('inf')), dict(fwd='1'), dict(fwd=True), dict(fwd=1.1),
    dict(emergency_stop='false'), dict(mode='unknown'), dict(nonce='bad'), dict(extra=1)])
def test_invalid_schema_is_rejected(pair, changes):
    tx, rx = pair
    pkt = packet(tx, **changes)
    # Non-finite wire values are rejected even before HMAC comparison.
    if changes.get('fwd') == float('inf'):
        data = json.dumps(dict(pkt, mac='a' * 64)).encode()
    else:
        data = link._encode(pkt, KEY)
    inject(tx, rx, data)
    assert rx._last_cmd_t is None


def test_deep_duplicate_and_oversized_json_are_rejected(pair):
    tx, rx = pair
    for data in (b'[' * 1200 + b']' * 1200, b'{"seq":1,"seq":2}', b'x' * 3000):
        inject(tx, rx, data)
    assert rx._last_cmd_t is None
    assert rx.stats()['parse_errors'] == 3


def test_udp_flood_poll_is_bounded(pair):
    _, rx = pair
    rx._sock.close()
    rx._sock = Mock()
    rx._sock.recvfrom.return_value = (b'{}', ('127.0.0.1', 1))
    rx.poll()
    assert rx._sock.recvfrom.call_count == link.MAX_POLL_PACKETS


def test_receiver_latches_estop_across_packets_and_staleness(pair):
    tx, rx = pair
    inject(tx, rx, link._encode(packet(tx, emergency_stop=True), KEY))
    inject(tx, rx, link._encode(packet(tx, seq=1, emergency_stop=False), KEY))
    cmd, _ = rx.get_command()
    assert cmd['emergency_stop'] is True
    assert cmd['fwd'] == 0
    rx._last_cmd_t = time.monotonic() - 10
    assert rx.get_command()[0]['emergency_stop'] is True


def test_sender_latches_estop_and_bypasses_rate_limit(pair):
    tx, rx = pair
    tx.send_interval_s = 100
    assert tx.send({'fwd': .5})
    assert tx.send({'emergency_stop': True})
    assert tx.send({})
    rx.poll()
    assert rx.get_command()[0]['emergency_stop'] is True


def test_explicit_simulation_works_without_key(monkeypatch):
    monkeypatch.delenv('CAKABEY_COMMAND_KEY', raising=False)
    rx = link.CommandReceiver(bind='127.0.0.1', port=0, allow_insecure=True)
    tx = link.CommandSender(host='127.0.0.1', port=rx._sock.getsockname()[1], allow_insecure=True)
    try:
        assert tx.send({'fwd': .2})
        rx.poll()
        assert rx.get_command()[0]['fwd'] == .2
    finally:
        tx.close()
        rx.close()
