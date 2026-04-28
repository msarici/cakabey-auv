"""
anomaly_detector.py — Boru Anomali Tespiti
Çakabey AUV | TEKNOCAK 2026

5 anomaly tipi (klasik CV, deterministik, Jetson dostu):
    - algae   : yosun         (HSV yeşil)
    - rust    : pas           (HSV koyu kırmızı/kahverengi)
    - crack   : çatlak        (Canny + HoughLinesP)
    - break   : kopma         (mask içinde 2+ ayrı contour)
    - missing : eksik parça   (geometri / aspect ratio sapması)

Pipeline:
    PipeDetector(detection) -> AnomalyDetector.detect(frame, detection)
    -> [{type, bbox, confidence, area_ratio}, ...]

Tasarım:
- FSM/PID'i bozmaz, sadece raporlar (telemetri + overlay).
- Boru bulunmadıysa erken döner; CPU israfı yok.
- Eşikler config'ten gelir; ABC ile tune edilebilir.
"""

import cv2
import numpy as np


class AnomalyDetector:
    ALGAE = "algae"
    RUST = "rust"
    CRACK = "crack"
    BREAK = "break"
    MISSING = "missing"

    def __init__(
        self,
        # algae (yosun) - HSV yeşil
        algae_h_min=35, algae_h_max=85,
        algae_s_min=40, algae_v_min=30,
        algae_ratio_thresh=0.05,
        # rust (pas) - HSV koyu kırmızı/kahverengi
        rust_h_min=0, rust_h_max=15,
        rust_s_min=80, rust_s_max=220,
        rust_v_min=30, rust_v_max=110,
        rust_ratio_thresh=0.03,
        # crack (çatlak) - HoughLinesP parametreleri
        crack_canny_low=50, crack_canny_high=150,
        crack_hough_thresh=20,
        crack_min_line_len=15,
        crack_max_line_gap=5,
        crack_min_lines=1,
        # break (kopma) - mask'teki contour sayısı
        break_min_contour_area=200,
        # break öncesi morfolojik close kernel'i: color-change delikleri
        # (rust/algae) bridgelensin ama gerçek pipe gap (>kernel) sağ kalsın.
        break_close_kernel_w=49,
        break_close_kernel_h=9,
        # missing (eksik parça) - aspect ratio (sadece "çok kısa" tetikler)
        missing_aspect_min=3.0,
    ):
        self.algae_h_min = algae_h_min
        self.algae_h_max = algae_h_max
        self.algae_s_min = algae_s_min
        self.algae_v_min = algae_v_min
        self.algae_ratio_thresh = algae_ratio_thresh

        self.rust_h_min = rust_h_min
        self.rust_h_max = rust_h_max
        self.rust_s_min = rust_s_min
        self.rust_s_max = rust_s_max
        self.rust_v_min = rust_v_min
        self.rust_v_max = rust_v_max
        self.rust_ratio_thresh = rust_ratio_thresh

        self.crack_canny_low = crack_canny_low
        self.crack_canny_high = crack_canny_high
        self.crack_hough_thresh = crack_hough_thresh
        self.crack_min_line_len = crack_min_line_len
        self.crack_max_line_gap = crack_max_line_gap
        self.crack_min_lines = crack_min_lines

        self.break_min_contour_area = break_min_contour_area
        self.break_close_kernel_w = max(1, int(break_close_kernel_w))
        self.break_close_kernel_h = max(1, int(break_close_kernel_h))

        self.missing_aspect_min = missing_aspect_min

    def detect(self, frame, detection):
        """
        frame: tam BGR frame
        detection: PipeDetector çıktısı (found, bbox, mask vb.)
        Returns: anomaly listesi. Her eleman:
            {"type", "bbox" (frame koordinatlarında), "confidence", "area_ratio"}
        """
        if not detection or not detection.get("found", False):
            return []

        bbox = detection.get("bbox", (0, 0, 0, 0))
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            return []

        full_mask = detection.get("mask")
        if full_mask is None:
            return []

        # ROI extract (frame ve mask aynı şekle sahip olmalı)
        fh, fw = frame.shape[:2]
        x2 = min(fw, x + w)
        y2 = min(fh, y + h)
        x = max(0, x)
        y = max(0, y)
        if x2 <= x or y2 <= y:
            return []

        roi = frame[y:y2, x:x2]
        roi_mask = full_mask[y:y2, x:x2]

        anomalies = []
        # Önce break/missing — break varsa crack'i bastırmak için.
        # Kopuk uçların kenar pikselleri çatlak olarak yanlış sınıflanmasın.
        struct_anoms = self._detect_break_and_missing(roi_mask, x, y)
        has_break = any(a["type"] == self.BREAK for a in struct_anoms)

        anomalies.extend(self._detect_algae(roi, roi_mask, x, y))
        anomalies.extend(self._detect_rust(roi, roi_mask, x, y))
        if not has_break:
            anomalies.extend(self._detect_crack(roi, roi_mask, x, y))
        anomalies.extend(struct_anoms)
        return anomalies

    @staticmethod
    def _pipe_pixels(roi_mask):
        return int(np.count_nonzero(roi_mask))

    @staticmethod
    def _largest_blob_bbox(binary_mask, offset_x, offset_y):
        """Binary mask içinde en büyük blob'un frame koordinatlı bbox'ı."""
        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None
        biggest = max(contours, key=cv2.contourArea)
        bx, by, bw, bh = cv2.boundingRect(biggest)
        return (bx + offset_x, by + offset_y, bw, bh)

    def _detect_algae(self, roi, roi_mask, off_x, off_y):
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower = np.array([self.algae_h_min, self.algae_s_min, self.algae_v_min], dtype=np.uint8)
        upper = np.array([self.algae_h_max, 255, 255], dtype=np.uint8)
        algae_mask = cv2.inRange(hsv, lower, upper)
        # ROI içinde yeşil (boru üstünde veya cevresinde)
        pipe_px = self._pipe_pixels(roi_mask)
        if pipe_px == 0:
            return []
        ratio = float(np.count_nonzero(algae_mask)) / float(pipe_px)
        if ratio < self.algae_ratio_thresh:
            return []
        bbox = self._largest_blob_bbox(algae_mask, off_x, off_y)
        if bbox is None:
            return []
        return [{
            "type": self.ALGAE,
            "bbox": bbox,
            "confidence": min(ratio / max(self.algae_ratio_thresh, 1e-6), 1.0),
            "area_ratio": ratio,
        }]

    def _detect_rust(self, roi, roi_mask, off_x, off_y):
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower = np.array([self.rust_h_min, self.rust_s_min, self.rust_v_min], dtype=np.uint8)
        upper = np.array([self.rust_h_max, self.rust_s_max, self.rust_v_max], dtype=np.uint8)
        rust_mask = cv2.inRange(hsv, lower, upper)
        # Pas pikselleri orange mask'in DIŞINDA görünür (turuncuyu örtmüş).
        # Bu yüzden roi_mask ile AND yapma; bbox zaten boru bölgesi.
        pipe_px = self._pipe_pixels(roi_mask)
        if pipe_px == 0:
            return []
        ratio = float(np.count_nonzero(rust_mask)) / float(pipe_px)
        if ratio < self.rust_ratio_thresh:
            return []
        bbox = self._largest_blob_bbox(rust_mask, off_x, off_y)
        if bbox is None:
            return []
        return [{
            "type": self.RUST,
            "bbox": bbox,
            "confidence": min(ratio / max(self.rust_ratio_thresh, 1e-6), 1.0),
            "area_ratio": ratio,
        }]

    def _detect_crack(self, roi, roi_mask, off_x, off_y):
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, self.crack_canny_low, self.crack_canny_high)
        # Boru sınırı kenarları (en üst/alt) tetiklemesin: bbox'ı içeri çek.
        # Çatlak orange mask'i koparttığı için mask-based erosion kullanılamaz
        # (çatlak pikselleri zaten mask'in dışına düşer); bbox tabanlı inner kullan.
        h, w = roi_mask.shape
        margin_y = max(2, h // 8)
        margin_x = max(2, w // 25)
        inner = np.zeros_like(roi_mask)
        if h > 2 * margin_y and w > 2 * margin_x:
            inner[margin_y:h - margin_y, margin_x:w - margin_x] = 255
        edges = cv2.bitwise_and(edges, inner)

        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180,
            threshold=self.crack_hough_thresh,
            minLineLength=self.crack_min_line_len,
            maxLineGap=self.crack_max_line_gap,
        )
        if lines is None or len(lines) < self.crack_min_lines:
            return []

        # Tüm line endpoint'lerini kapsayan bbox
        xs = []
        ys = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            xs.extend([x1, x2])
            ys.extend([y1, y2])
        bx = int(min(xs))
        by = int(min(ys))
        bw = int(max(xs) - bx)
        bh = int(max(ys) - by)

        n_lines = len(lines)
        confidence = min(n_lines / max(self.crack_min_lines * 3, 1), 1.0)
        return [{
            "type": self.CRACK,
            "bbox": (bx + off_x, by + off_y, max(bw, 1), max(bh, 1)),
            "confidence": confidence,
            "area_ratio": float(n_lines),  # crack için "ratio" yerine line count
        }]

    def _detect_break_and_missing(self, roi_mask, off_x, off_y):
        """
        Kopma: ROI-mask içinde 2+ büyük contour varsa (gap görünüyor).
        Eksik: tek contour ama aspect ratio beklenenden düşükse.

        ÖNEMLİ: full mask değil, sadece detection bbox'ına kırpılmış mask
        kullanılır. Boru dışında kalan turuncu distractor'lar break tetiklemez.

        Color-change anomalileri (rust/algae) boru üzerinde mask'i koparır
        ama bu bir "kopma" değildir. Önce horizontal-biased MORPH_CLOSE ile
        bu küçük delikler bridge edilir; gerçek pipe break (kernel'den geniş
        gap) sağ kalır.
        """
        kernel = np.ones((self.break_close_kernel_h, self.break_close_kernel_w),
                         np.uint8)
        closed = cv2.morphologyEx(roi_mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        big_contours = [c for c in contours
                        if cv2.contourArea(c) >= self.break_min_contour_area]

        out = []

        if len(big_contours) >= 2:
            # Kopma: ROI içinde en az 2 ayrı parça
            xs = []
            ys = []
            xes = []
            yes = []
            for c in big_contours:
                cx, cy, cw, ch = cv2.boundingRect(c)
                xs.append(cx); ys.append(cy)
                xes.append(cx + cw); yes.append(cy + ch)
            bx = min(xs); by = min(ys)
            bw = max(xes) - bx; bh = max(yes) - by
            out.append({
                "type": self.BREAK,
                # ROI-local koordinatları frame koordinatlarına çevir
                "bbox": (bx + off_x, by + off_y, bw, bh),
                "confidence": min(len(big_contours) / 2.0, 1.0),
                "area_ratio": float(len(big_contours)),
            })
            return out  # kopma varsa missing kontrol etme (zaten bozuk)

        # Eksik parça: tek parça ama aspect ratio çok düşük (boru kesilmiş)
        # NOT: long pipe (aspect büyük) normal — sadece "çok kısa" tetiklensin.
        rh, rw = roi_mask.shape
        if rh > 0:
            aspect = rw / float(rh)
            if aspect < self.missing_aspect_min:
                out.append({
                    "type": self.MISSING,
                    "bbox": (off_x, off_y, rw, rh),
                    "confidence": min((self.missing_aspect_min - aspect) / self.missing_aspect_min, 1.0),
                    "area_ratio": aspect,
                })
        return out
