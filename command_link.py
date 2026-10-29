"""Authenticated UDP control channel.

Set CAKABEY_COMMAND_KEY to the same random secret (at least 32 UTF-8 bytes)
on both machines. An HMAC-authenticated hello/challenge binds commands to a
receiver-issued nonce with a short lease, sender session and increasing sequence.
The receiver pins the first command sender session until restart. Emergency stop
is latched at both ends until restart. Explicit allow_insecure is for simulation.
"""

import hashlib
import hmac
import json
import math
import os
import secrets
import socket
import time

MAX_DATAGRAM = 2048
MAX_POLL_PACKETS = 64
NONCE_LEASE_S = 2.0
HELLO_INTERVAL_S = 0.5


def _clamp(v, lo=-1.0, hi=1.0):
    try:
        v = float(v)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return max(lo, min(hi, v))


def _key(value, enabled, allow_insecure):
    value = os.environ.get('CAKABEY_COMMAND_KEY', '') if value is None else value
    value = value.encode('utf-8') if isinstance(value, str) else value
    if not enabled or allow_insecure:
        return None
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError('CAKABEY_COMMAND_KEY must contain at least 32 bytes; '
                         'use enabled=False for autonomous-only operation')
    return value


def _canonical(pkt):
    return json.dumps(pkt, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _encode(pkt, key):
    wire = dict(pkt)
    if key is not None:
        wire['mac'] = hmac.new(key, _canonical(pkt), hashlib.sha256).hexdigest()
    return _canonical(wire)


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate JSON field')
        obj[key] = value
    return obj


def _decode(data, key):
    if len(data) > MAX_DATAGRAM:
        raise ValueError('oversized command')
    pkt = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_pairs)
    if not isinstance(pkt, dict):
        raise ValueError('expected object')
    if key is not None:
        mac = pkt.pop('mac', None)
        if not isinstance(mac, str) or len(mac) != 64:
            raise ValueError('missing authentication')
        expected = hmac.new(key, _canonical(pkt), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError('invalid authentication')
    return pkt


def _token(value):
    return isinstance(value, str) and len(value) == 32 and all(c in '0123456789abcdef' for c in value)


def _valid_command(pkt):
    fields = {'kind', 'session', 'nonce', 'seq', 'ts', 'mode', 'fwd', 'yaw', 'vertical', 'emergency_stop'}
    if set(pkt) != fields or pkt['kind'] != 'command':
        return False
    if not _token(pkt['session']) or not _token(pkt['nonce']):
        return False
    if type(pkt['seq']) is not int or not 0 <= pkt['seq'] < 2**63:
        return False
    if type(pkt['ts']) not in (int, float) or not math.isfinite(pkt['ts']):
        return False
    if pkt['mode'] not in ('auto', 'manual') or type(pkt['emergency_stop']) is not bool:
        return False
    return all(type(pkt[k]) in (int, float) and math.isfinite(pkt[k]) and -1 <= pkt[k] <= 1
               for k in ('fwd', 'yaw', 'vertical'))


class CommandSender:
    def __init__(self, host='192.168.2.2', port=14653, enabled=True,
                 send_interval_s=0.02, auth_key=None, allow_insecure=False):
        self.host, self.port = host, int(port)
        self.enabled = bool(enabled)
        self.send_interval_s = float(send_interval_s)
        self._key = _key(auth_key, self.enabled, allow_insecure)
        self._session = secrets.token_hex(16)
        self._nonce = '0' * 32 if allow_insecure else None
        self._request = None
        self._hello_seq = 0
        self._last_hello = float('-inf')
        self._estop = False
        self._sock = None
        self._seq = 0
        self._last_send_t = float('-inf')
        self._send_errors = 0
        self._dropped_rate = 0
        if self.enabled:
            self._open_socket()

    def _open_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setblocking(False)
            self._sock = sock
        except OSError:
            sock.close()
            raise

    def _handshake(self, now):
        if self._key is None:
            return
        for _ in range(MAX_POLL_PACKETS):
            try:
                data, _ = self._sock.recvfrom(MAX_DATAGRAM + 1)
            except BlockingIOError:
                break
            try:
                pkt = _decode(data, self._key)
                if (set(pkt) == {'kind', 'session', 'request', 'nonce'} and
                        pkt['kind'] == 'challenge' and pkt['session'] == self._session and
                        pkt['request'] == self._request and _token(pkt['nonce'])):
                    self._nonce = pkt['nonce']
                    self._request = None
            except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
                continue
        if now - self._last_hello >= HELLO_INTERVAL_S:
            self._request = secrets.token_hex(16)
            self._sock.sendto(_encode({'kind': 'hello', 'session': self._session,
                                      'request': self._request, 'hello_seq': self._hello_seq}, self._key), (self.host, self.port))
            self._hello_seq += 1
            self._last_hello = now

    def send(self, input_dict, mode='manual'):
        if not self.enabled or self._sock is None:
            return False
        if not isinstance(input_dict, dict):
            return False
        self._estop = self._estop or input_dict.get('emergency_stop') is True
        now = time.monotonic()
        try:
            self._handshake(now)
            if self._nonce is None:
                return False
            if not self._estop and now - self._last_send_t < self.send_interval_s:
                self._dropped_rate += 1
                return False
            pkt = {'kind': 'command', 'session': self._session, 'nonce': self._nonce,
                   'seq': self._seq, 'ts': now,
                   'mode': 'auto' if str(mode).lower() == 'auto' else 'manual',
                   'fwd': _clamp(input_dict.get('fwd', 0)),
                   'yaw': _clamp(input_dict.get('yaw', 0)),
                   'vertical': _clamp(input_dict.get('vertical', 0)),
                   'emergency_stop': self._estop}
            self._sock.sendto(_encode(pkt, self._key), (self.host, self.port))
            self._seq += 1
            self._last_send_t = now
            return True
        except (OSError, InterruptedError):
            self._send_errors += 1
            return False

    def stats(self):
        return {'seq': self._seq, 'dropped_rate': self._dropped_rate,
                'send_errors': self._send_errors}

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None


class CommandReceiver:
    def __init__(self, bind='0.0.0.0', port=14653, stale_after_s=0.5,
                 auth_key=None, allow_insecure=False, enabled=True):
        self.bind, self.port = bind, int(port)
        self.stale_after_s = float(stale_after_s)
        if not math.isfinite(self.stale_after_s) or self.stale_after_s <= 0:
            raise ValueError('stale_after_s must be finite and positive')
        self.enabled = bool(enabled)
        self._key = _key(auth_key, self.enabled, allow_insecure)
        self._nonce = '0' * 32 if allow_insecure else None
        self._nonce_t = None
        self._challenge_session = None
        self._last_hello_seq = -1
        self._session = None
        self._estop = False
        self._sock = None
        self._last_cmd = None
        self._last_cmd_t = None
        self._last_seq = -1
        self._recv_count = self._recv_errors = self._parse_errors = self._lost_packets = 0
        if self.enabled:
            self._open_socket()

    def _open_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 18)
            sock.bind((self.bind, self.port))
            sock.setblocking(False)
            self._sock = sock
        except OSError:
            sock.close()
            raise

    def poll(self):
        if self._sock is None:
            return
        # Bound work so UDP flooding cannot monopolize the vehicle safety loop.
        for _ in range(MAX_POLL_PACKETS):
            try:
                data, addr = self._sock.recvfrom(MAX_DATAGRAM + 1)
            except BlockingIOError:
                break
            except OSError:
                self._recv_errors += 1
                break
            try:
                pkt = _decode(data, self._key)
                if (self._key is not None and set(pkt) == {'kind', 'session', 'request', 'hello_seq'} and
                        pkt['kind'] == 'hello' and _token(pkt['session']) and _token(pkt['request']) and
                        type(pkt['hello_seq']) is int and 0 <= pkt['hello_seq'] < 2**63):
                    if self._session is not None and self._session != pkt['session']:
                        raise ValueError('sender session locked')
                    if self._challenge_session == pkt['session'] and pkt['hello_seq'] <= self._last_hello_seq:
                        raise ValueError('replayed hello')
                    self._last_hello_seq = pkt['hello_seq']
                    self._nonce = secrets.token_hex(16)
                    self._nonce_t = time.monotonic()
                    self._challenge_session = pkt['session']
                    self._sock.sendto(_encode({'kind': 'challenge', 'session': pkt['session'],
                                              'request': pkt['request'], 'nonce': self._nonce}, self._key), addr)
                    continue
                if not _valid_command(pkt):
                    raise ValueError('invalid command schema')
                if pkt['nonce'] != self._nonce:
                    raise ValueError('invalid receiver nonce')
                if self._key is not None and (pkt['session'] != self._challenge_session or
                        self._nonce_t is None or time.monotonic() - self._nonce_t > NONCE_LEASE_S):
                    raise ValueError('expired challenge')
                if self._session is not None and self._session != pkt['session']:
                    raise ValueError('sender session locked')
                if pkt['seq'] <= self._last_seq:
                    raise ValueError('duplicate or reordered command')
                if self._last_seq >= 0:
                    self._lost_packets += pkt['seq'] - self._last_seq - 1
                self._session = pkt['session']
                self._last_seq = pkt['seq']
                self._estop = self._estop or pkt['emergency_stop']
                self._last_cmd = pkt
                self._last_cmd_t = time.monotonic()
                self._recv_count += 1
            except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
                self._parse_errors += 1
            except OSError:
                self._recv_errors += 1

    def get_command(self):
        if self._last_cmd is None or self._last_cmd_t is None:
            return self._safe_default(), False
        age = time.monotonic() - self._last_cmd_t
        if age > self.stale_after_s:
            return self._safe_default(stale=True), True
        cmd = self._last_cmd
        return {'mode': cmd['mode'], 'fwd': 0.0 if self._estop else cmd['fwd'],
                'yaw': 0.0 if self._estop else cmd['yaw'],
                'vertical': 0.0 if self._estop else cmd['vertical'],
                'emergency_stop': self._estop, 'seq': cmd['seq'], 'age': age, 'stale': False}, False

    def _safe_default(self, stale=False):
        return {'mode': 'auto', 'fwd': 0.0, 'yaw': 0.0, 'vertical': 0.0,
                'emergency_stop': self._estop, 'seq': -1, 'age': None, 'stale': stale}

    def stats(self):
        return {'recv_count': self._recv_count, 'lost_packets': self._lost_packets,
                'recv_errors': self._recv_errors, 'parse_errors': self._parse_errors,
                'last_seq': self._last_seq}

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None
