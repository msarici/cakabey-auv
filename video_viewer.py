"""
video_viewer.py — Yer Istasyonu (Standalone)
Cakabey AUV | TEKNOCAK 2026

Laptop'ta calisir. Iki sey yapar:
1) ROV'dan UDP MJPEG akisini al, parcalari birlestir, ekrana bas.
2) Klavye/gamepad'i oku, ROV'a UDP komut paketi gonder.

Tek pygame penceresi, 60 FPS event loop. pygame.surfarray ile cv2
frame'i ekrana yansitilir; cv2.imshow KULLANILMIYOR cunku pygame
event'leri ile cakisiyor.

Mod mantigi:
- M tusu (klavye) / A (gamepad) basildiginda mod toggle: manual <-> auto.
- SPACE / B = emergency_stop, mod bagimsiz motorlari sifirlar (ROV tarafi).
- ESC = cik.

Kullanim:
    python video_viewer.py --rov-ip 192.168.2.2 --video-port 14652 \
        --cmd-port 14653 --input auto
"""

import argparse
import struct
import socket
import sys
import time

import numpy as np
import cv2
import pygame

from manual_input import ManualInput
from command_link import CommandSender

HEADER = struct.Struct(">IHH")
HEADER_SIZE = HEADER.size

# Frame reassembly icin reorder buffer.
# Eski/disinda frame'ler atilir. Pratikte 2-3 frame yeter.
REASSEMBLY_BUFFER = 4
RECV_BUFFER_BYTES = 1 << 20  # 1 MB OS recv buffer


class FrameReceiver:
    def __init__(self, bind="0.0.0.0", port=14652):
        self.bind = bind
        self.port = int(port)

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RECV_BUFFER_BYTES)
        except OSError:
            pass
        self._sock.bind((bind, self.port))
        self._sock.setblocking(False)

        # {frame_id: {"total": N, "chunks": {chunk_id: bytes}, "ts": t}}
        self._partial = {}
        self._last_complete_id = -1
        self._frames_received = 0
        self._frames_dropped = 0  # tamamlanmadi
        self._frames_decoded = 0
        self._decode_errors = 0

    def poll(self):
        """Non-blocking: kuyruktaki tum paketleri ic, hazir frame varsa
        bgr numpy array dondur. Yoksa None."""
        latest_frame = None

        while True:
            try:
                data, _addr = self._sock.recvfrom(65535)
            except BlockingIOError:
                break
            except OSError:
                break

            if len(data) < HEADER_SIZE:
                continue

            fid, cid, total = HEADER.unpack(data[:HEADER_SIZE])
            payload = data[HEADER_SIZE:]

            # Yeni frame_id geldi, eskilerini temizle
            if fid <= self._last_complete_id and self._last_complete_id - fid > REASSEMBLY_BUFFER:
                # Frame_id wraparound veya gercekten eski; goz ardi et
                continue

            entry = self._partial.get(fid)
            if entry is None:
                entry = {"total": total, "chunks": {}, "ts": time.monotonic()}
                self._partial[fid] = entry
            elif entry["total"] != total:
                # Bozuk paket: header'da farkli total. Reset.
                entry["total"] = total
                entry["chunks"] = {}

            entry["chunks"][cid] = payload

            if len(entry["chunks"]) == entry["total"]:
                # Tamamlandi. Sirali birlestir.
                try:
                    blob = b"".join(entry["chunks"][i] for i in range(entry["total"]))
                except KeyError:
                    # Eksik chunk (race), drop
                    self._frames_dropped += 1
                    self._partial.pop(fid, None)
                    continue

                self._partial.pop(fid, None)
                self._last_complete_id = max(self._last_complete_id, fid)
                self._frames_received += 1

                # Decode
                try:
                    arr = np.frombuffer(blob, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        latest_frame = img
                        self._frames_decoded += 1
                    else:
                        self._decode_errors += 1
                except Exception:
                    self._decode_errors += 1

        # Eski partial'lari sil (timeout)
        now = time.monotonic()
        stale = [k for k, v in self._partial.items() if now - v["ts"] > 1.0]
        for k in stale:
            self._partial.pop(k, None)
            self._frames_dropped += 1

        return latest_frame

    def stats(self):
        return {
            "frames_received": self._frames_received,
            "frames_decoded": self._frames_decoded,
            "frames_dropped": self._frames_dropped,
            "decode_errors": self._decode_errors,
        }

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


def bgr_to_surface(frame_bgr):
    """OpenCV BGR -> pygame Surface."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb = np.rot90(rgb)
    rgb = np.flipud(rgb)
    return pygame.surfarray.make_surface(rgb)


def render_hud(screen, mode, cmd_dict, fps, frame_stats, link_alive):
    """Sol ust koseye HUD bilgisi cizdir."""
    font = pygame.font.SysFont("consolas", 18)
    lines = [
        f"MODE: {mode.upper()}",
        f"FWD: {cmd_dict.get('fwd', 0.0):+.2f}  YAW: {cmd_dict.get('yaw', 0.0):+.2f}  VRT: {cmd_dict.get('vertical', 0.0):+.2f}",
        f"VIEW FPS: {fps:.1f}",
        f"RX frames: {frame_stats.get('frames_decoded', 0)}  drop: {frame_stats.get('frames_dropped', 0)}",
        f"LINK: {'OK' if link_alive else 'NO VIDEO'}",
        "M=mode  SPACE=ESTOP  ESC=cik",
    ]
    y = 10
    for line in lines:
        # arkaplana yari saydam siyah serit
        surf = font.render(line, True, (255, 255, 255))
        bg = pygame.Surface((surf.get_width() + 10, surf.get_height() + 4))
        bg.set_alpha(140)
        bg.fill((0, 0, 0))
        screen.blit(bg, (8, y - 2))
        screen.blit(surf, (13, y))
        y += surf.get_height() + 2


def main():
    parser = argparse.ArgumentParser(description="Cakabey Yer Istasyonu")
    parser.add_argument("--rov-ip", default="192.168.2.2",
                        help="ROV IP (komut hedefi)")
    parser.add_argument("--bind", default="0.0.0.0",
                        help="Video dinleme IP")
    parser.add_argument("--video-port", type=int, default=14652)
    parser.add_argument("--cmd-port", type=int, default=14653)
    parser.add_argument("--input", default="auto",
                        choices=["auto", "keyboard", "gamepad"])
    parser.add_argument("--width", type=int, default=960,
                        help="Pencere genisligi (frame yoksa baslangic)")
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--no-cmd", action="store_true",
                        help="Komut gonderme; sadece video izle.")
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_caption("Cakabey AUV — Yer Istasyonu")
    screen = pygame.display.set_mode((args.width, args.height), pygame.RESIZABLE)
    clock = pygame.time.Clock()

    try:
        manual = ManualInput(source=args.input)
    except RuntimeError as e:
        print(f"[viewer] manual_input init hatasi: {e}")
        sys.exit(1)

    sender = None if args.no_cmd else CommandSender(
        host=args.rov_ip, port=args.cmd_port, send_interval_s=0.02
    )

    rx = FrameReceiver(bind=args.bind, port=args.video_port)

    print(f"[viewer] Video dinleniyor {args.bind}:{args.video_port}")
    if sender:
        print(f"[viewer] Komut hedefi {args.rov_ip}:{args.cmd_port}")
    print(f"[viewer] Input: {manual.source}")

    mode = "manual"
    last_frame = None
    last_frame_t = 0.0
    fps_frames = 0
    fps_start = time.time()
    view_fps = 0.0

    try:
        while True:
            # 1) Pygame events (ESC ve pencere kapatma)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise KeyboardInterrupt
                if event.type == pygame.VIDEORESIZE:
                    screen = pygame.display.set_mode(
                        (event.w, event.h), pygame.RESIZABLE
                    )

            # 2) Manuel input oku (tek-shot tuslar dahil)
            inp = manual.read()
            if inp["mode_toggle"]:
                mode = "auto" if mode == "manual" else "manual"
                print(f"[viewer] Mode -> {mode}")

            # 3) Komut gonder
            if sender:
                sender.send(inp, mode=mode)

            # 4) Video al
            new_frame = rx.poll()
            if new_frame is not None:
                last_frame = new_frame
                last_frame_t = time.monotonic()

            link_alive = (time.monotonic() - last_frame_t) < 1.5

            # 5) Cizdir
            screen.fill((10, 10, 14))
            if last_frame is not None:
                surf = bgr_to_surface(last_frame)
                # Pencereyi orana sigdir
                w, h = screen.get_size()
                fh, fw = last_frame.shape[:2]
                scale = min(w / fw, h / fh)
                target = (int(fw * scale), int(fh * scale))
                surf = pygame.transform.smoothscale(surf, target)
                offset = ((w - target[0]) // 2, (h - target[1]) // 2)
                screen.blit(surf, offset)
            else:
                font = pygame.font.SysFont("consolas", 22)
                msg = font.render("Video bekleniyor...", True, (200, 200, 200))
                screen.blit(msg, (20, screen.get_height() // 2))

            render_hud(screen, mode, inp, view_fps, rx.stats(), link_alive)
            pygame.display.flip()

            # 6) FPS sayaci
            fps_frames += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                view_fps = fps_frames / elapsed
                fps_frames = 0
                fps_start = time.time()

            clock.tick(60)

    except KeyboardInterrupt:
        print("\n[viewer] Kapatiliyor...")
    finally:
        rx.close()
        if sender:
            sender.close()
        manual.close()
        pygame.quit()


if __name__ == "__main__":
    main()
