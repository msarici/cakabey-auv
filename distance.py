"""
distance.py — Mesafe Tahmini
Çakabey AUV | TEKNOCAK 2026

Pinhole veya paralel lazer tabanlı mesafe hesabı.
Aktif yöntem config.yaml içindeki distance.method ile seçilir.
"""


class DistanceEstimator:
    PINHOLE = "pinhole"
    LASER = "laser"

    def __init__(
        self,
        method="pinhole",
        pipe_real_width_cm=20.0,
        focal_length_px=500.0,
        laser_baseline_cm=15.0,
    ):
        if focal_length_px <= 0:
            raise ValueError(f"focal_length_px > 0 olmalı, alındı: {focal_length_px}")
        if pipe_real_width_cm <= 0:
            raise ValueError(f"pipe_real_width_cm > 0 olmalı, alındı: {pipe_real_width_cm}")
        if laser_baseline_cm <= 0:
            raise ValueError(f"laser_baseline_cm > 0 olmalı, alındı: {laser_baseline_cm}")

        self.method = method
        self.pipe_real_width_cm = pipe_real_width_cm
        self.focal_length_px = focal_length_px
        self.laser_baseline_cm = laser_baseline_cm

    def estimate(self, bbox_width=None, laser_pixel_gap=None):
        """
        Aktif yönteme göre mesafe döndürür.
        Yöntem için gerekli giriş yoksa None döner.
        """
        if self.method == self.PINHOLE:
            return self.from_bbox(bbox_width)

        if self.method == self.LASER:
            return self.from_lasers(laser_pixel_gap)

        return None

    def from_bbox(self, bbox_width_px):
        """
        Pinhole modeli: D = (W * f) / w
        W: bilinen gerçek genişlik (cm)
        f: kamera focal length (px)
        w: ölçülen bbox genişliği (px)
        """
        if bbox_width_px is None or bbox_width_px <= 0:
            return None
        return (self.pipe_real_width_cm * self.focal_length_px) / bbox_width_px

    def from_lasers(self, laser_pixel_gap):
        """
        Paralel lazer demet yöntemi (Pilgrim et al. 2000).
        D = (B * f) / g
        B: lazerler arası baseline (cm)
        f: kamera focal length (px)
        g: görüntüdeki iki lazer arası piksel mesafesi
        """
        if laser_pixel_gap is None or laser_pixel_gap <= 0:
            return None
        return (self.laser_baseline_cm * self.focal_length_px) / laser_pixel_gap