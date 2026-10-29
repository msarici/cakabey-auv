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
try:
    import pygame
except ImportError:
    pygame = None

from manual_input import ManualInput
from command_link import CommandSender

HEADER = struct.Struct(">IHH")
HEADER_SIZE = HEADER.size

# Frame reassembly icin reorder buffer.
# Eski/disinda frame'ler atilir. Pratikte 2-3 frame yeter.
REASSEMBLY_BUFFER = 4
RECV_BUFFER_BYTES = 1 << 20  # 1 MB OS recv buffer
MAX_PACKETS_PER_POLL = 128
MAX_DECODES_PER_POLL = 4
MAX_CHUNKS = 64
MAX_CHUNK_BYTES = 60000
MAX_FRAME_BYTES = 4 << 20
FRAME_TIMEOUT = 1.0
MAX_IMAGE_PIXELS = 3840 * 2160


def _jpeg_dimensions_allowed(blob):
    """Check JPEG SOF dimensions before OpenCV allocates the decoded image."""
    if not blob.startswith(b"\xff\xd8"):
        return False
    pos = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
           0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while pos < len(blob):
        if blob[pos] != 0xFF:
            return False
        while pos < len(blob) and blob[pos] == 0xFF:
            pos += 1
        if pos >= len(blob):
            return False
        marker = blob[pos]
        pos += 1
        if marker in (0xD9, 0xDA):
            return False
        if pos + 2 > len(blob):
            return False
        length = int.from_bytes(blob[pos:pos + 2], "big")
        if length < 2 or pos + length > len(blob):
            return False
        if marker in sof:
            if length < 8:
                return False
            height = int.from_bytes(blob[pos + 3:pos + 5], "big")
            width = int.from_bytes(blob[pos + 5:pos + 7], "big")
            return 0 < width <= 4096 and 0 < height <= 4096 and width * height <= MAX_IMAGE_PIXELS
        pos += length
    return False


class FrameReceiver:
    def __init__(self, bind="0.0.0.0", port=14652, source_host=None):
        self.bind = bind
        self.port = int(port)
        self.source_host = socket.gethostbyname(source_host) if source_host is not None else None
        self._last_complete_t = None

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
        """Bound processing so video traffic cannot starve control/UI events."""
        latest_frame = None
        decodes = 0
        now = time.monotonic()
        # Allow a sender restarted at frame 0 after an idle interval.
        if self._last_complete_t is not None and now - self._last_complete_t > FRAME_TIMEOUT:
            self._last_complete_id = -1
            self._last_complete_t = None
        for fid in list(self._partial):
            if now - self._partial[fid]["ts"] > FRAME_TIMEOUT:
                self._partial.pop(fid)
                self._frames_dropped += 1

        for _ in range(MAX_PACKETS_PER_POLL):
            try:
                data, addr = self._sock.recvfrom(65535)
            except (BlockingIOError, OSError):
                break
            if self.source_host is not None and addr[0] != self.source_host:
                continue
            if len(data) <= HEADER_SIZE or len(data) > HEADER_SIZE + MAX_CHUNK_BYTES:
                continue
            fid, cid, total = HEADER.unpack(data[:HEADER_SIZE])
            if not 1 <= total <= MAX_CHUNKS or cid >= total:
                continue
            if self._last_complete_id >= 0:
                delta = (fid - self._last_complete_id) & 0xFFFFFFFF
                if not 0 < delta < 0x80000000:
                    continue
            payload = data[HEADER_SIZE:]
            entry = self._partial.get(fid)
            if entry is None:
                if len(self._partial) >= REASSEMBLY_BUFFER:
                    oldest = min(self._partial, key=lambda key: self._partial[key]["ts"])
                    self._partial.pop(oldest)
                    self._frames_dropped += 1
                entry = {"total": total, "chunks": {}, "ts": now, "bytes": 0}
                self._partial[fid] = entry
            elif entry["total"] != total:
                continue
            if cid in entry["chunks"]:
                continue
            entry["bytes"] += len(payload)
            if entry["bytes"] > MAX_FRAME_BYTES:
                self._partial.pop(fid)
                self._frames_dropped += 1
                continue
            entry["chunks"][cid] = payload
            if len(entry["chunks"]) != total:
                continue
            blob = b"".join(entry["chunks"][i] for i in range(total))
            self._partial.pop(fid)
            if not _jpeg_dimensions_allowed(blob):
                self._decode_errors += 1
                continue
            decodes += 1
            try:
                img = cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_COLOR)
            except Exception:
                img = None
            if img is None:
                self._decode_errors += 1
                if decodes >= MAX_DECODES_PER_POLL:
                    break
                continue
            latest_frame = img
            self._last_complete_id = fid
            self._last_complete_t = now
            self._frames_received += 1
            self._frames_decoded += 1
            if decodes >= MAX_DECODES_PER_POLL:
                break
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
    parser.add_argument("--sim", action="store_true",
                        help="Yerel donanımsız test; kimliksiz komut yalnızca loopback")
    parser.add_argument("--no-cmd", action="store_true",
                        help="Komut gonderme; sadece video izle.")
    args = parser.parse_args()
    if args.sim and args.rov_ip != "127.0.0.1":
        parser.error("--sim için --rov-ip 127.0.0.1 gerekli")

    if pygame is None:
        raise SystemExit("pygame gerekli: pip install pygame")
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
        host=args.rov_ip, port=args.cmd_port, allow_insecure=args.sim, send_interval_s=0.02
    )

    rx = FrameReceiver(bind=args.bind, port=args.video_port, source_host=args.rov_ip)

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
