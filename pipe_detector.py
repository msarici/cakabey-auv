"""
pipe_detector.py — Boru Tespit Modülü
Çakabey AUV | TEKNOCAK 2026

HSV maskeleme ile turuncu boruyu bulmaya çalışır.
En büyük uygun contour seçilir.
"""

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
            "area": int(best_area),
            "error_x": int(error_x),
            "error_y": int(error_y),
            "width": bw,
            "height": bh,
            "frame_center": (center_x, center_y),
            "mask": mask,
        }

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
        value = int(value)
        if value < 1:
            value = 1
        if value % 2 == 0:
            value += 1
        return value