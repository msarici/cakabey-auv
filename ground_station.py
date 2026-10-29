"""
ground_station.py — Kara İstasyonuna UDP Telemetri
Çakabey AUV | TEKNOCAK 2026

Tasarım:
- UDP fire-and-forget (ack beklemez, asla bloklanmaz)
- JSON payload (insan-okunur, debug kolay)
- Rate limit: main loop FPS'inden bağımsız, send_interval_s ile ayarlanır
- Hata sessiz: socket hatası loop'u durdurmasın (network düşse devam etmeli)
- Sequence number: kara tarafında paket kaybı tespit edilebilir
- CAT6 tether üzerinden çalışır (UDP IPv4)
"""

import json
import socket
import time

from telemetry_auth import DatagramAuthenticator, loopback_address


class GroundStation:
    def __init__(self, host="192.168.2.1", port=14651, enabled=True,
                 send_interval_s=0.1, auth_key=None, allow_insecure=False):
        """
        host: kara istasyonu IP (ROV tether default genelde 192.168.2.1)
        port: UDP destination port
        enabled: False ise hiç socket açmaz, send() no-op
        send_interval_s: ardışık iki paket arası minimum süre (rate limit)
        """
        self.host = loopback_address(host) if allow_insecure and enabled else host
        self._auth = DatagramAuthenticator("telemetry", auth_key, allow_insecure, enabled)
        self.port = int(port)
        self.enabled = bool(enabled)
        self.send_interval_s = float(send_interval_s)

        self._sock = None
        self._seq = 0
        self._last_send_t = 0.0
        self._dropped_due_to_rate = 0
        self._send_errors = 0

        if self.enabled:
            self._open_socket()

    def _open_socket(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Safety loop must never wait for a congested network.
            self._sock.setblocking(False)
        except Exception as e:
            print(f"[ground] Socket acilamadi: {e}")
            self._sock = None
            self.enabled = False

    def _build_packet(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Telemetry payload must be a dictionary")
        packet = dict(payload)
        packet.update(seq=self._seq, ts=time.time())
        return packet

    def send(self, payload):
        """
        payload: dict (state, detection, sensor, control, fps, anomalies, vb.)
        Rate limit'e uymuyorsa sessizce drop edilir.
        Network hatası raise etmez; sadece sayaca yazılır.
        Returns: True (gönderildi), False (drop veya hata).
        """
        if not self.enabled or self._sock is None:
            return False

        now = time.monotonic()
        if now - self._last_send_t < self.send_interval_s:
            self._dropped_due_to_rate += 1
            return False

        try:
            packet = self._build_packet(payload)
            data = self._auth.encode(json.dumps(packet, allow_nan=False).encode("utf-8"))
            self._sock.sendto(data, (self.host, self.port))
            self._seq += 1
            self._last_send_t = now
            return True
        except (ValueError, TypeError, OverflowError, RecursionError):
            self._send_errors += 1
            return False
        except (BlockingIOError, InterruptedError, socket.timeout):
            # UDP send buffer dolu — nadir; sadece sayaca yaz
            self._send_errors += 1
            return False
        except OSError as e:
            self._send_errors += 1
            # Network down: 1 sn'de bir uyarı verecek kadar gürültüsüz tut
            if self._send_errors == 1 or self._send_errors % 100 == 0:
                print(f"[ground] UDP send hatasi (#{self._send_errors}): {e}")
            return False

    def stats(self):
        return {
            "seq": self._seq,
            "dropped_rate": self._dropped_due_to_rate,
            "send_errors": self._send_errors,
        }

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
