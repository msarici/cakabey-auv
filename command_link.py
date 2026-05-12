"""
command_link.py — Yer Istasyonu -> ROV UDP Komut Kanali
Cakabey AUV | TEKNOCAK 2026

Iki sinif:
- CommandSender (laptop tarafi): manuel input dict'ini paketleyip atar.
- CommandReceiver (ROV tarafi): non-blocking UDP okur, son komutu
  cache'ler. Watchdog: paket eskirse motorlar=0.

Protokol (JSON, UDP, fire-and-forget):
    {
      "seq": int,
      "ts": float,        # sender monotonic ts
      "mode": "manual" | "auto",
      "fwd": -1.0..1.0,
      "yaw": -1.0..1.0,
      "vertical": -1.0..1.0,
      "emergency_stop": bool
    }

Tasarim notlari:
- Komut paketleri telemetri ve videodan ayri portta (default 14653).
- Sender rate-limit'li (50Hz default). Receiver son paketi tutar.
- Receiver tarafi watchdog: stale_after_s gecince motorlari 0'a indir.
- ROV restart olsa bile receiver socket re-bind etmesi gerek; bunu
  open()/close() ile yonet.
"""

import json
import socket
import time


def _clamp(v, lo=-1.0, hi=1.0):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(lo, min(hi, v))


class CommandSender:
    """Laptop tarafinda calisir. send(input_dict, mode) -> UDP."""

    def __init__(self, host="192.168.2.2", port=14653, enabled=True,
                 send_interval_s=0.02):
        """
        host: ROV IP (laptop'tan bakildiginda).
        send_interval_s: 0.02 = 50 Hz. Kontrol icin yeterli, bant az.
        """
        self.host = host
        self.port = int(port)
        self.enabled = bool(enabled)
        self.send_interval_s = float(send_interval_s)

        self._sock = None
        self._seq = 0
        self._last_send_t = 0.0
        self._send_errors = 0
        self._dropped_rate = 0

        if self.enabled:
            self._open_socket()

    def _open_socket(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(0.05)
        except Exception as e:
            print(f"[cmd_tx] Socket acilamadi: {e}")
            self._sock = None
            self.enabled = False

    def send(self, input_dict, mode="manual"):
        """
        input_dict: ManualInput.read() ciktisi veya benzeri dict.
        mode: "manual" / "auto"
        Returns: True / False.
        """
        if not self.enabled or self._sock is None:
            return False

        now = time.monotonic()
        if now - self._last_send_t < self.send_interval_s:
            self._dropped_rate += 1
            return False

        try:
            payload = {
                "seq": self._seq,
                "ts": now,
                "mode": "auto" if str(mode).lower() == "auto" else "manual",
                "fwd": _clamp((input_dict or {}).get("fwd", 0.0)),
                "yaw": _clamp((input_dict or {}).get("yaw", 0.0)),
                "vertical": _clamp((input_dict or {}).get("vertical", 0.0)),
                "emergency_stop": bool((input_dict or {}).get("emergency_stop", False)),
            }
            data = json.dumps(payload).encode("utf-8")
            self._sock.sendto(data, (self.host, self.port))
            self._seq += 1
            self._last_send_t = now
            return True
        except (BlockingIOError, InterruptedError, socket.timeout):
            self._send_errors += 1
            return False
        except OSError as e:
            self._send_errors += 1
            if self._send_errors == 1 or self._send_errors % 100 == 0:
                print(f"[cmd_tx] UDP send hatasi (#{self._send_errors}): {e}")
            return False

    def stats(self):
        return {
            "seq": self._seq,
            "dropped_rate": self._dropped_rate,
            "send_errors": self._send_errors,
        }

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None


class CommandReceiver:
    """ROV tarafinda calisir. Non-blocking UDP, son komutu cache."""

    def __init__(self, bind="0.0.0.0", port=14653, stale_after_s=0.5):
        """
        bind: dinleme IP (genelde 0.0.0.0).
        port: UDP port.
        stale_after_s: paket bundan eskiyse "stale" sayilir, motorlar 0.
        """
        self.bind = bind
        self.port = int(port)
        self.stale_after_s = float(stale_after_s)

        self._sock = None
        self._last_cmd = None
        self._last_cmd_t = None  # monotonic local
        self._last_seq = -1
        self._recv_count = 0
        self._recv_errors = 0
        self._parse_errors = 0
        self._lost_packets = 0
        self._open_socket()

    def _open_socket(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 50Hz burst gelirse default kuyruk yetmez (Windows loopback'te
            # ozellikle). 256 KB iyi marj.
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 18)
            except OSError:
                pass
            self._sock.bind((self.bind, self.port))
            self._sock.setblocking(False)
        except Exception as e:
            print(f"[cmd_rx] Bind hatasi {self.bind}:{self.port}: {e}")
            self._sock = None

    def poll(self):
        """
        Non-blocking, kuyrukta ne kadar paket varsa hepsini cek; son
        gecerli komutu cache'le. Cagrim hizi loop FPS'i kadar olabilir.
        """
        if self._sock is None:
            return

        while True:
            try:
                data, _addr = self._sock.recvfrom(65535)
            except BlockingIOError:
                break
            except OSError:
                self._recv_errors += 1
                break

            try:
                pkt = json.loads(data.decode("utf-8"))
            except Exception:
                self._parse_errors += 1
                continue

            if not isinstance(pkt, dict):
                self._parse_errors += 1
                continue

            seq = pkt.get("seq", -1)
            if isinstance(seq, int) and not isinstance(seq, bool):
                if self._last_seq >= 0 and seq > self._last_seq + 1:
                    self._lost_packets += seq - self._last_seq - 1
                self._last_seq = seq

            self._last_cmd = pkt
            self._last_cmd_t = time.monotonic()
            self._recv_count += 1

    def get_command(self):
        """
        Son gelen komutu dondur. Eskimisse "safe" komut donder:
            mode=auto, tum eksenler 0, emergency_stop=False
        (mode=auto secimi sebebi: stale link -> FSM kontrole geri donsun,
         laptop devre disi kalsa bile arac belirsizlikte donmesin.)
        """
        if self._last_cmd is None or self._last_cmd_t is None:
            return self._safe_default(), False

        age = time.monotonic() - self._last_cmd_t
        if age > self.stale_after_s:
            return self._safe_default(stale=True), True

        cmd = self._last_cmd
        return {
            "mode": "manual" if str(cmd.get("mode", "auto")).lower() == "manual" else "auto",
            "fwd": _clamp(cmd.get("fwd", 0.0)),
            "yaw": _clamp(cmd.get("yaw", 0.0)),
            "vertical": _clamp(cmd.get("vertical", 0.0)),
            "emergency_stop": bool(cmd.get("emergency_stop", False)),
            "seq": cmd.get("seq", -1),
            "age": age,
            "stale": False,
        }, False

    def _safe_default(self, stale=False):
        return {
            "mode": "auto",
            "fwd": 0.0,
            "yaw": 0.0,
            "vertical": 0.0,
            "emergency_stop": False,
            "seq": -1,
            "age": None,
            "stale": stale,
        }

    def stats(self):
        return {
            "recv_count": self._recv_count,
            "lost_packets": self._lost_packets,
            "recv_errors": self._recv_errors,
            "parse_errors": self._parse_errors,
            "last_seq": self._last_seq,
        }

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
