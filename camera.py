"""
camera.py — Kamera Modülü
Çakabey AUV | TEKNOCAK 2026
Yazar: Mert Sarıcı

CSI kamera, webcam veya test modu ile görüntü verir.
Kamera açılamazsa test moduna düşer.
"""

import time
import cv2
import numpy as np


class Camera:
    def __init__(self, source="test", width=640, height=480, fps=30, device_id=0, allow_test_fallback=False):
        """
        allow_test_fallback: gerçek kamera açılmazsa test moduna düşmesine izin
        verir. Production (görev) için False olmalı; geliştirme/test için True.
        """
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.device_id = device_id
        self.allow_test_fallback = allow_test_fallback

        self.cap = None
        self.frame_count = 0
        self.fps_start = time.time()
        self.current_fps = 0.0

    def open(self):
        if self.source == "csi":
            pipeline = self._gstreamer_pipeline()
            self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        elif self.source == "webcam":
            self.cap = cv2.VideoCapture(self.device_id)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        elif self.source == "test":
            self.cap = None
            print("[kamera] Test modu aktif.")
            return True

        else:
            print(f"[kamera] Geçersiz kaynak: {self.source}.")
            self.cap = None
            return False

        if self.cap is None or not self.cap.isOpened():
            if self.allow_test_fallback:
                print(f"[kamera] {self.source} açılamadı. Test moduna geçiliyor (fallback aktif).")
                self.source = "test"
                self.cap = None
                return True
            print(f"[kamera] {self.source} açılamadı. Fallback kapalı, hata raporlanıyor.")
            self.cap = None
            return False

        print(f"[kamera] {self.source} açıldı. ({self.width}x{self.height})")
        return True

    def read(self):
        if self.source == "test":
            # CPU %100'ü engellemek için target FPS'e göre rate limit
            if self.fps > 0:
                target_dt = 1.0 / self.fps
                now = time.time()
                last = getattr(self, "_last_test_read", None)
                if last is not None:
                    elapsed = now - last
                    if elapsed < target_dt:
                        time.sleep(target_dt - elapsed)
                self._last_test_read = time.time()
            frame = self._generate_test_frame()
            self._update_fps()
            return frame

        if self.cap is None:
            return None

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None

        self._update_fps()
        return frame

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        print("[kamera] Kamera kapatıldı.")

    def _gstreamer_pipeline(self):
        return (
            f"nvarguscamerasrc ! "
            f"video/x-raw(memory:NVMM), width={self.width}, height={self.height}, "
            f"format=NV12, framerate={self.fps}/1 ! "
            f"nvvidconv ! video/x-raw, format=BGRx ! "
            f"videoconvert ! video/x-raw, format=BGR ! "
            f"appsink drop=1"
        )

    def _generate_test_frame(self):
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:, :] = (55, 45, 25)

        t = time.time()
        cx = int(self.width // 2 + 100 * np.sin(t * 0.6))
        cy = int(self.height // 2 + 30 * np.cos(t * 0.4))

        cv2.rectangle(
            frame,
            (cx - 80, cy - 18),
            (cx + 80, cy + 18),
            (0, 115, 245),
            -1
        )

        noise = np.random.randint(0, 12, frame.shape, dtype=np.uint8)
        frame = cv2.add(frame, noise)
        return frame

    def _update_fps(self):
        self.frame_count += 1
        elapsed = time.time() - self.fps_start

        if elapsed >= 1.0:
            self.current_fps = self.frame_count / elapsed
            self.frame_count = 0
            self.fps_start = time.time()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Camera test")
    parser.add_argument("--source", default="test", choices=["csi", "webcam", "test"])
    parser.add_argument("--device-id", type=int, default=0)
    args = parser.parse_args()

    cam = Camera(source=args.source, device_id=args.device_id)
    cam.open()

    print("Çıkmak için q bas.")

    while True:
        frame = cam.read()
        if frame is None:
            print("[kamera] Frame alınamadı.")
            break

        cv2.putText(
            frame,
            f"FPS: {cam.current_fps:.0f}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2
        )

        cv2.imshow("Camera Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cam.close()
    cv2.destroyAllWindows()