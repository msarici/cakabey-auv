"""
pipe_detector.py — Boru Tespit Modülü
Çakabey AUV | TEKNOCAK 2026

HSV maskeleme ile turuncu boruyu bulmaya çalışır.
En büyük uygun contour seçilir.

LIMITASYON — H wraparound:
OpenCV'de H kanalı 0-179 dairesel. cv2.inRange tek aralık ile çalışır,
yani örnek olarak kırmızı (H ≈ 0 ve H ≈ 179'a yakın) için iki ayrı
maske alıp bitwise_or yapmak gerekir. Turuncu (H ≈ 5-25) wraparound
bölgesinde değil, mevcut tek-aralık yaklaşımı yeterli. Hedef renk
değişirse bu sınırlama gözden geçirilmeli.
"""

import math

import cv2
import numpy as np


class PipeDetector:
    def __init__(
        self,
        h_min=10,
        h_max=25,
        s_min=100,
        s_max=255,
        v_min=80,
        v_max=255,
        min_area=500,
        blur_kernel=5,
        morph_kernel=5,
    ):
        for name, low, high, maximum in (("H", h_min, h_max, 179),
                                         ("S", s_min, s_max, 255),
                                         ("V", v_min, v_max, 255)):
            if any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) or int(value) != value for value in (low, high)):
                raise ValueError(f"{name} thresholds must be finite integers")
            if not 0 <= low <= high <= maximum:
                raise ValueError(f"{name} thresholds must satisfy 0 <= min <= max <= {maximum}")
        if not math.isfinite(min_area) or min_area <= 0:
            raise ValueError("min_area must be positive and finite")
        self.h_min = h_min
        self.h_max = h_max
        self.s_min = s_min
        self.s_max = s_max
        self.v_min = v_min
        self.v_max = v_max
        self.min_area = min_area

        # OpenCV kernel'ları tek sayı olmalı
        self.blur_kernel = self._make_valid_kernel(blur_kernel)
        self.morph_kernel = self._make_valid_kernel(morph_kernel)

    def detect(self, frame):
        h, w = frame.shape[:2]
        center_x = w // 2
        center_y = h // 2

        # blur
        if self.blur_kernel > 1:
            frame_blur = cv2.GaussianBlur(frame, (self.blur_kernel, self.blur_kernel), 0)
        else:
            frame_blur = frame

        # hsv
        hsv = cv2.cvtColor(frame_blur, cv2.COLOR_BGR2HSV)

        lower = np.array([self.h_min, self.s_min, self.v_min], dtype=np.uint8)
        upper = np.array([self.h_max, self.s_max, self.v_max], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        # morph
        kernel = np.ones((self.morph_kernel, self.morph_kernel), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_contour = None
        best_area = 0.0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue

            if area > best_area:
                best_area = area
                best_contour = cnt

        if best_contour is None:
            return self._empty_result(center_x, center_y, mask)

        x, y, bw, bh = cv2.boundingRect(best_contour)
        anomaly_bbox, anomaly_mask = self._anomaly_region(contours, best_contour, mask)

        # merkez hesabı moments ile daha hassas
        m = cv2.moments(best_contour)
        if m["m00"] != 0:
            cx = int(m["m10"] / m["m00"])
            cy = int(m["m01"] / m["m00"])
        else:
            cx = x + bw // 2
            cy = y + bh // 2

        # KRİTİK:
        # boru sağdaysa hata pozitif olsun
        error_x = cx - center_x
        error_y = cy - center_y

        return {
            "found": True,
            "cx": cx,
            "cy": cy,
            "bbox": (x, y, bw, bh),
            "anomaly_bbox": anomaly_bbox,
            "anomaly_mask": anomaly_mask,
            "area": int(best_area),
            "error_x": int(error_x),
            "error_y": int(error_y),
            "width": bw,
            "height": bh,
            "frame_center": (center_x, center_y),
            "mask": mask,
        }

    def _anomaly_region(self, contours, anchor, mask):
        """Group nearby collinear fragments for inspection, not motor steering.

        A broken pipe has multiple contours. The control target remains the
        largest contour; inspection may include aligned fragments across a gap
        of at most four pipe thicknesses. Off-axis distractors stay excluded.
        """
        box = cv2.boxPoints(cv2.minAreaRect(anchor))
        edges = np.roll(box, -1, axis=0) - box
        lengths = np.linalg.norm(edges, axis=1)
        axis = edges[int(np.argmax(lengths))] / max(float(max(lengths)), 1.0)
        normal = np.array([-axis[1], axis[0]])
        pts = anchor.reshape(-1, 2)
        across = pts @ normal
        thickness = max(float(np.ptp(across)), 1.0)
        center = float(np.mean([across.min(), across.max()]))
        along = pts @ axis
        lo, hi = float(along.min()), float(along.max())
        chosen = [anchor]
        remaining = [c for c in contours if c is not anchor and cv2.contourArea(c) >= self.min_area]
        # At most one pass per contour; expansion supports multiple occlusions.
        for _ in range(len(remaining)):
            added = False
            for c in list(remaining):
                p = c.reshape(-1, 2)
                cross, axial = p @ normal, p @ axis
                width = float(np.ptp(cross))
                if not 0.5 * thickness <= width <= 1.5 * thickness:
                    continue
                if abs(float((cross.min() + cross.max()) / 2) - center) > 0.35 * thickness:
                    continue
                c_lo, c_hi = float(axial.min()), float(axial.max())
                gap = max(lo - c_hi, c_lo - hi, 0)
                if gap > 4 * thickness:
                    continue
                chosen.append(c)
                remaining = [other for other in remaining if other is not c]
                lo, hi = min(lo, c_lo), max(hi, c_hi)
                added = True
            if not added:
                break
        region_mask = np.zeros_like(mask)
        cv2.drawContours(region_mask, chosen, -1, 255, cv2.FILLED)
        # Preserve real holes (algae/rust/crack); contour filling is only a selector.
        region_mask = cv2.bitwise_and(mask, region_mask)
        bbox = cv2.boundingRect(np.concatenate(chosen))
        return bbox, region_mask

    def _empty_result(self, center_x, center_y, mask):
        return {
            "found": False,
            "cx": 0,
            "cy": 0,
            "bbox": (0, 0, 0, 0),
            "area": 0,
            "error_x": 0,
            "error_y": 0,
            "width": 0,
            "height": 0,
            "frame_center": (center_x, center_y),
            "mask": mask,
        }

    @staticmethod
    def _make_valid_kernel(value):
        if not math.isfinite(value) or value > 255:
            raise ValueError("kernel size must be finite and <= 255")
        value = int(value)
        if value < 1:
            value = 1
        if value % 2 == 0:
            value += 1
        return value