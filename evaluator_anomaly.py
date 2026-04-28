"""
evaluator_anomaly.py — Anomali Tespiti için Sentetik Dataset
Çakabey AUV | TEKNOCAK 2026

Donanım yokken AnomalyDetector'ı doğrulamak için kontrollü sentetik
frame'ler üretir. Her frame'in tek bir anomaly tipi vardır (yosun, pas,
çatlak, kopma, eksik) veya temizdir (clean).

Üretilen frame BGR'dir. Boru turuncu (HSV ~ 10-25), arka plan koyu
kahverengi, gürültü düşük (deterministik).

API:
    gen = AnomalyDataset(seed=42)
    frame, gt_label = gen.make("algae")
    # gt_label "algae" ise frame içinde yosun var; "clean" ise yok.

Kullanım: testlerde + ABC tuning yapıldığında fitness fonksiyonu olarak.
"""

import numpy as np
import cv2


class AnomalyDataset:
    LABELS = ("clean", "algae", "rust", "crack", "break", "missing")

    def __init__(self, width=640, height=480, seed=42):
        self.width = width
        self.height = height
        self.rng = np.random.RandomState(seed)

    def _blank_frame(self):
        # Koyu kahverengi/sualtı arka plan
        bg = np.full((self.height, self.width, 3), (55, 45, 25), dtype=np.uint8)
        return bg

    def _draw_pipe(self, frame, x_left, x_right, y_center=None, thickness=36):
        if y_center is None:
            y_center = self.height // 2
        y1 = y_center - thickness // 2
        y2 = y_center + thickness // 2
        # Boru turuncu (HSV H~12, S~255, V~245)
        cv2.rectangle(frame, (x_left, y1), (x_right, y2), (0, 115, 245), -1)
        return (x_left, y1, x_right - x_left, y2 - y1)

    def _add_noise(self, frame, std=8):
        noise = self.rng.normal(0, std, frame.shape).astype(np.int16)
        return np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # ---------- her label için frame üretici ----------

    def _make_clean(self):
        frame = self._blank_frame()
        bbox = self._draw_pipe(frame, 120, 520)
        return self._add_noise(frame), bbox

    def make_clean_with_distractor(self):
        """
        Temiz boru + boru bbox'ı dışında ayrı bir turuncu distractor.
        Boru detection bbox'ına sınırlı analiz break tetiklememeli.
        """
        frame = self._blank_frame()
        bbox = self._draw_pipe(frame, 120, 520)
        # Boru'nun ALTINDA, bbox dışında ikinci bir turuncu blok (distractor)
        cv2.rectangle(frame, (200, 380), (380, 420), (0, 115, 245), -1)
        return self._add_noise(frame), bbox

    def _make_algae(self):
        """Boru üzerine birkaç yeşil leke."""
        frame = self._blank_frame()
        bbox = self._draw_pipe(frame, 120, 520)
        # 3 yeşil yosun lekesi (BGR koyu yeşil)
        for cx in (200, 320, 420):
            cy = self.height // 2 + self.rng.randint(-8, 9)
            r = self.rng.randint(14, 22)
            cv2.circle(frame, (cx, cy), r, (40, 130, 50), -1)
        return self._add_noise(frame), bbox

    def _make_rust(self):
        """Boru üzerinde koyu kırmızı/kahverengi pas lekeleri."""
        frame = self._blank_frame()
        bbox = self._draw_pipe(frame, 120, 520)
        # Pas: BGR koyu kahverengi (HSV ~ H=10, S=180, V=70)
        for cx in (220, 350):
            cy = self.height // 2 + self.rng.randint(-6, 7)
            r = self.rng.randint(16, 24)
            cv2.circle(frame, (cx, cy), r, (15, 40, 75), -1)
        return self._add_noise(frame), bbox

    def _make_crack(self):
        """Boru üzerinde ince koyu çizgiler (çatlak)."""
        frame = self._blank_frame()
        bbox = self._draw_pipe(frame, 120, 520)
        cy = self.height // 2
        # Birkaç ince diagonal çizgi
        cv2.line(frame, (200, cy - 12), (240, cy + 12), (0, 0, 0), 2)
        cv2.line(frame, (320, cy - 14), (370, cy + 14), (0, 0, 0), 2)
        cv2.line(frame, (430, cy - 10), (470, cy + 10), (0, 0, 0), 2)
        return self._add_noise(frame), bbox

    def _make_break(self):
        """Boru iki ayrı parça (ortada gap)."""
        frame = self._blank_frame()
        # Sol parça
        self._draw_pipe(frame, 120, 290)
        # Sağ parça (gap = 60 px)
        self._draw_pipe(frame, 350, 520)
        # bbox tüm range'i kapsar
        bbox = (120, self.height // 2 - 18, 400, 36)
        return self._add_noise(frame), bbox

    def _make_missing(self):
        """Boru ucu kesilmiş — kısa tek parça (aspect ratio bozuk)."""
        frame = self._blank_frame()
        # Çok kısa boru parçası (60 px wide x 36 high → aspect ~1.7, missing range altı)
        bbox = self._draw_pipe(frame, 280, 340)
        return self._add_noise(frame), bbox

    def make(self, label):
        if label == "clean":
            frame, bbox = self._make_clean()
        elif label == "algae":
            frame, bbox = self._make_algae()
        elif label == "rust":
            frame, bbox = self._make_rust()
        elif label == "crack":
            frame, bbox = self._make_crack()
        elif label == "break":
            frame, bbox = self._make_break()
        elif label == "missing":
            frame, bbox = self._make_missing()
        else:
            raise ValueError(f"Bilinmeyen label: {label}")
        return frame, bbox


def detection_from_frame(frame, bbox):
    """
    AnomalyDetector için minimal PipeDetector çıktısı:
    HSV turuncu mask + bbox.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (5, 100, 80), (25, 255, 255))
    return {
        "found": True,
        "bbox": bbox,
        "mask": mask,
        "cx": bbox[0] + bbox[2] // 2,
        "cy": bbox[1] + bbox[3] // 2,
        "area": int(np.count_nonzero(mask)),
        "width": bbox[2],
        "height": bbox[3],
    }


if __name__ == "__main__":
    gen = AnomalyDataset()
    for label in gen.LABELS:
        frame, bbox = gen.make(label)
        print(f"  {label:8s} bbox={bbox} shape={frame.shape}")
