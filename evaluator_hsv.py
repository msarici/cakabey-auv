"""
evaluator_hsv.py — HSV Tuning için IoU Evaluator
Çakabey AUV | TEKNOCAK 2026

Sentetik test frame'leri üzerinde HSV parametre setinin
ne kadar iyi mask çıkardığını IoU metriği ile ölçer.

Dataset zorlaştırılmıştır:
- Gaussian noise eklendi (gerçek kamera koşullarına yakınlık)
- Distractor objeler: kırmızı ve sarı bloklar (HSV'yi turuncu özelinde
  ayarlamaya zorlar, yakın renkleri eleyecek)
- Arka plan çeşitliliği: her frame farklı tonda kahverengi/yeşilimsi
  (V kanalına overfitting'i engeller)

Bu zorlaştırmalar gerçek su altı koşullarını tam temsil etmez ancak
algoritmanın gürültü ve benzer renkler altında robust olduğunu kanıtlar.
"""

import time
import numpy as np
import cv2

from pipe_detector import PipeDetector


class HSVEvaluator:
    def __init__(self, num_frames=20, frame_width=640, frame_height=480, seed=42):
        self.num_frames = num_frames
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Deterministik dataset için seed sabitle
        # ABC her fitness çağrısında aynı dataset'i görmeli
        self.rng = np.random.RandomState(seed)

        self.frames = []
        self.gt_masks = []
        self._prepare_dataset()

    def _prepare_dataset(self):
        """20 zorlaştırılmış sentetik frame ve ground truth mask üret."""
        for i in range(self.num_frames):
            t = time.time() + i * 0.3
            frame, gt_mask = self._make_frame_and_gt(t, frame_idx=i)
            self.frames.append(frame)
            self.gt_masks.append(gt_mask)

    def _make_frame_and_gt(self, t, frame_idx):
        """
        Belirli bir zaman ve frame indeksi için frame ve ground truth üret.
        frame_idx farklı arka plan/distractor kombinasyonu için kullanılır.
        """
        # 1. ARKA PLAN ÇEŞİTLİLİĞİ
        # Her frame'de hafifçe farklı koyu ton
        bg_b = 55 + (frame_idx * 7) % 30   # 55-85 arası
        bg_g = 45 + (frame_idx * 5) % 25   # 45-70 arası
        bg_r = 25 + (frame_idx * 3) % 20   # 25-45 arası
        frame = np.full((self.frame_height, self.frame_width, 3), (bg_b, bg_g, bg_r), dtype=np.uint8)

        # 2. DISTRACTOR OBJELER
        # Kırmızı blok (sol üstte) - HSV H ≈ 0-5
        cv2.rectangle(frame, (50, 50), (130, 110), (30, 30, 200), -1)
        # Sarı blok (sağ altta) - HSV H ≈ 25-30 (turuncuya yakın!)
        cv2.rectangle(frame, (510, 380), (600, 440), (40, 230, 230), -1)

        # 3. HEDEF: TURUNCU BORU
        # Pozisyon zamana göre değişiyor (kamera.py mantığı)
        cx = int(self.frame_width // 2 + 100 * np.sin(t * 0.6))
        cy = int(self.frame_height // 2 + 30 * np.cos(t * 0.4))

        cv2.rectangle(
            frame,
            (cx - 80, cy - 18),
            (cx + 80, cy + 18),
            (0, 115, 245),  # gerçek turuncu
            -1
        )

        # 4. GAUSSIAN NOISE
        # std=12 → gerçekçi sensör gürültüsü
        noise = self.rng.normal(0, 12, frame.shape).astype(np.int16)
        frame_noisy = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # 5. GROUND TRUTH MASK
        # Sadece turuncu boru, distractor'lar dahil değil
        gt_mask = np.zeros((self.frame_height, self.frame_width), dtype=np.uint8)
        cv2.rectangle(
            gt_mask,
            (cx - 80, cy - 18),
            (cx + 80, cy + 18),
            255,
            -1
        )

        return frame_noisy, gt_mask

    def evaluate(self, hsv_params):
        """
        ABC bu fonksiyonu çağırıyor.
        Tüm frame'lerin ortalama IoU'sunu döndürür.
        """
        detector = PipeDetector(
            h_min=hsv_params["h_min"],
            h_max=hsv_params["h_max"],
            s_min=hsv_params["s_min"],
            s_max=hsv_params["s_max"],
            v_min=hsv_params["v_min"],
            v_max=hsv_params["v_max"],
            min_area=100,
            blur_kernel=5,
            morph_kernel=5,
        )

        ious = []
        for frame, gt_mask in zip(self.frames, self.gt_masks):
            result = detector.detect(frame)
            pred_mask = result.get("mask")

            if pred_mask is None:
                ious.append(0.0)
                continue

            iou = self._compute_iou(pred_mask, gt_mask)
            ious.append(iou)

        return float(np.mean(ious))

    @staticmethod
    def _compute_iou(pred_mask, gt_mask):
        pred_bin = (pred_mask > 127).astype(np.uint8)
        gt_bin = (gt_mask > 127).astype(np.uint8)

        intersection = np.logical_and(pred_bin, gt_bin).sum()
        union = np.logical_or(pred_bin, gt_bin).sum()

        if union == 0:
            return 0.0

        return intersection / union


if __name__ == "__main__":
    evaluator = HSVEvaluator(num_frames=20)

    default_params = {
        "h_min": 10, "h_max": 25,
        "s_min": 100, "s_max": 255,
        "v_min": 80, "v_max": 255,
    }

    score = evaluator.evaluate(default_params)
    print(f"Zorlaştırılmış dataset, default HSV ile IoU: {score:.4f}")