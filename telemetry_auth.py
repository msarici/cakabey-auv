"""Bounded HMAC envelopes for one-way telemetry/video (no encryption).

Receivers pin a sender session until restart and reject duplicate/old sequences.
A signed wall-clock timestamp bounds delayed packets to two seconds; machines
must have synchronized clocks. Unlike the bidirectional command handshake, this
cannot eliminate capture/replay within the freshness window after viewer restart.
"""
import hashlib
import hmac
import ipaddress
import math
import os
import secrets
import socket
import struct
import time

_HEADER = struct.Struct('>4sB16sQd')
MAC_SIZE = 32
OVERHEAD = _HEADER.size + MAC_SIZE
MAX_WIRE_SIZE = 65507
MAX_AGE_S = 2.0
FUTURE_TOLERANCE_S = 0.5


def loopback_address(host):
    resolved = socket.gethostbyname(host)
    if not ipaddress.ip_address(resolved).is_loopback:
        raise ValueError('Unauthenticated simulation requires a loopback address')
    return resolved


class DatagramAuthenticator:
    def __init__(self, channel, auth_key=None, allow_insecure=False, enabled=True,
                 reorder_window=0):
        if channel not in ('telemetry', 'video'):
            raise ValueError('Unknown channel')
        self._channel = 1 if channel == 'telemetry' else 2
        key = os.environ.get('CAKABEY_COMMAND_KEY', '') if auth_key is None else auth_key
        key = key.encode('utf-8') if isinstance(key, str) else key
        self._key = None
        if enabled and not allow_insecure:
            if not isinstance(key, bytes) or len(key) < 32:
                raise ValueError('CAKABEY_COMMAND_KEY must contain at least 32 bytes')
            # Domain separation from the command protocol and between streams.
            self._key = hmac.new(key, b'cakabey-stream-v1/' + channel.encode(), hashlib.sha256).digest()
        self._session = secrets.token_bytes(16)
        self._seq = 0
        self._peer_session = None
        self._highest = -1
        self._seen = set()
        self._window = int(reorder_window)
        if not 0 <= self._window <= 256:
            raise ValueError('Invalid reordering window')

    def encode(self, payload):
        if len(payload) + (OVERHEAD if self._key else 0) > MAX_WIRE_SIZE:
            raise ValueError('UDP payload too large')
        if self._key is None:
            return payload
        header = _HEADER.pack(b'CAU1', self._channel, self._session, self._seq, time.time())
        body = header + payload
        self._seq += 1
        return body + hmac.new(self._key, body, hashlib.sha256).digest()

    def decode(self, wire):
        if len(wire) > MAX_WIRE_SIZE:
            raise ValueError('Oversized datagram')
        if self._key is None:
            return wire
        if len(wire) <= OVERHEAD:
            raise ValueError('Missing authenticated envelope')
        body, mac = wire[:-MAC_SIZE], wire[-MAC_SIZE:]
        expected = hmac.new(self._key, body, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError('Invalid authentication')
        magic, channel, session, seq, sent_at = _HEADER.unpack(body[:_HEADER.size])
        if magic != b'CAU1' or channel != self._channel or not math.isfinite(sent_at):
            raise ValueError('Invalid envelope')
        age = time.time() - sent_at
        if not -FUTURE_TOLERANCE_S <= age <= MAX_AGE_S:
            raise ValueError('Expired or future datagram; check machine clocks')
        if self._peer_session is not None and session != self._peer_session:
            raise ValueError('Sender session changed; restart viewer')
        if seq in self._seen or seq <= self._highest - self._window:
            raise ValueError('Duplicate or old datagram')
        self._peer_session = session
        self._highest = max(self._highest, seq)
        self._seen.add(seq)
        floor = self._highest - self._window
        self._seen = {n for n in self._seen if n >= floor}
        return body[_HEADER.size:]
