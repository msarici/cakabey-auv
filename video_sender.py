"""
video_sender.py — Yer Istasyonuna UDP MJPEG Video
Cakabey AUV | TEKNOCAK 2026

Tasarim:
- ROV'da calisir, her frame'i JPEG'e sikistirir, UDP'den atar.
- Fire-and-forget: ack beklemez, asla bloklanmaz.
- Chunked: JPEG buyukse parcalara boler (UDP MTU/datagram limiti).
- Rate limit: main loop FPS'inden bagimsiz, send_interval_s ile.
- Hata sessiz: socket hatasi loop'u dusurmesin.
- CAT6 tether (UDP IPv4) uzerinden calisir.

Paket formati (binary, 8 byte header + payload):
    [uint32 frame_id BE][uint16 chunk_id BE][uint16 total_chunks BE][JPEG bytes]
Alici frame_id ile parcalari birlestirir. Eksik chunk varsa frame drop.
"""

import socket
import struct
import time

import cv2

HEADER = struct.Struct(">IHH")
HEADER_SIZE = HEADER.size
# UDP datagram pratik max ~65507. Guvenli olsun diye 60000 secelim;
# CAT6 jumbo frame yoksa fragmente edilir ama IP layer hallediyor.
MAX_CHUNK_PAYLOAD = 60000


class VideoSender:
    def __init__(self, host="192.168.2.1", port=14652, enabled=True,
                 send_interval_s=0.066, jpeg_quality=60, max_width=640):
        """
        host/port: yer istasyonu UDP hedefi.
        enabled: False ise socket acmaz, send() no-op.
        send_interval_s: ardisik iki frame arasi min sure (rate limit).
            0.066 ~ 15 FPS. Bant geniliginden tutumlu.
        jpeg_quality: 1..100. 60 dengeli (~30-50 KB per 480p frame).
        max_width: frame bundan buyukse downscale edilir (CPU/bant tasarrufu).
        """
        self.host = host
        self.port = int(port)
        self.enabled = bool(enabled)
        self.send_interval_s = float(send_interval_s)
        self.jpeg_quality = int(jpeg_quality)
        self.max_width = int(max_width)

        self._sock = None
        self._frame_id = 0
        self._last_send_t = 0.0
        self._dropped_rate = 0
        self._send_errors = 0
        self._frames_sent = 0
        self._bytes_sent = 0

        if self.enabled:
            self._open_socket()

    def _open_socket(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(0.05)
        except Exception as e:
            print(f"[video] Socket acilamadi: {e}")
            self._sock = None
            self.enabled = False

    def send(self, frame):
        """
        frame: BGR numpy array (OpenCV).
        Returns: True (gonderildi), False (drop / hata / disabled).
        """
        if not self.enabled or self._sock is None or frame is None:
            return False

        now = time.monotonic()
        if now - self._last_send_t < self.send_interval_s:
            self._dropped_rate += 1
            return False

        try:
            # Downscale (genis frame'leri bant icin kucult).
            h, w = frame.shape[:2]
            if w > self.max_width:
                scale = self.max_width / float(w)
                new_w = self.max_width
                new_h = int(h * scale)
                frame = cv2.resize(frame, (new_w, new_h),
                                   interpolation=cv2.INTER_AREA)

            ok, jpg = cv2.imencode(
                ".jpg", frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            )
            if not ok:
                self._send_errors += 1
                return False

            data = jpg.tobytes()
            total_size = len(data)
            total_chunks = max(1, (total_size + MAX_CHUNK_PAYLOAD - 1) // MAX_CHUNK_PAYLOAD)
            # uint16 total_chunks: 65535 limit. Pratikte asla cikamayiz.
            if total_chunks > 0xFFFF:
                self._send_errors += 1
                return False

            fid = self._frame_id & 0xFFFFFFFF
            for chunk_id in range(total_chunks):
                start = chunk_id * MAX_CHUNK_PAYLOAD
                end = min(start + MAX_CHUNK_PAYLOAD, total_size)
                payload = data[start:end]
                header = HEADER.pack(fid, chunk_id, total_chunks)
                self._sock.sendto(header + payload, (self.host, self.port))

            self._frame_id = (self._frame_id + 1) & 0xFFFFFFFF
            self._last_send_t = now
            self._frames_sent += 1
            self._bytes_sent += total_size + HEADER_SIZE * total_chunks
            return True

        except (BlockingIOError, InterruptedError, socket.timeout):
            self._send_errors += 1
            return False
        except OSError as e:
            self._send_errors += 1
            if self._send_errors == 1 or self._send_errors % 100 == 0:
                print(f"[video] UDP send hatasi (#{self._send_errors}): {e}")
            return False
        except Exception as e:
            self._send_errors += 1
            if self._send_errors == 1 or self._send_errors % 100 == 0:
                print(f"[video] Beklenmedik hata (#{self._send_errors}): {e}")
            return False

    def stats(self):
        return {
            "frame_id": self._frame_id,
            "frames_sent": self._frames_sent,
            "bytes_sent": self._bytes_sent,
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
