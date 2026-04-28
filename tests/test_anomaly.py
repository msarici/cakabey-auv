"""
test_anomaly.py — AnomalyDetector için sentetik dataset testleri
Her tip için pozitif (anomaly var) ve negatif (clean'de yok) doğrulanır.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anomaly_detector import AnomalyDetector
from evaluator_anomaly import AnomalyDataset, detection_from_frame


def _detect(detector, label):
    gen = AnomalyDataset()
    frame, bbox = gen.make(label)
    detection = detection_from_frame(frame, bbox)
    return detector.detect(frame, detection)


def _types(anomalies):
    return {a["type"] for a in anomalies}


# ---------- pozitif testler: her tip kendi frame'inde bulunmalı ----------

def test_algae_detected_on_algae_frame():
    det = AnomalyDetector()
    types = _types(_detect(det, "algae"))
    assert AnomalyDetector.ALGAE in types


def test_rust_detected_on_rust_frame():
    det = AnomalyDetector()
    types = _types(_detect(det, "rust"))
    assert AnomalyDetector.RUST in types


def test_crack_detected_on_crack_frame():
    det = AnomalyDetector()
    types = _types(_detect(det, "crack"))
    assert AnomalyDetector.CRACK in types


def test_break_detected_on_break_frame():
    det = AnomalyDetector()
    types = _types(_detect(det, "break"))
    assert AnomalyDetector.BREAK in types


def test_missing_detected_on_missing_frame():
    det = AnomalyDetector()
    types = _types(_detect(det, "missing"))
    assert AnomalyDetector.MISSING in types


# ---------- negatif testler: clean frame'de yok ----------

def test_clean_frame_has_no_anomalies():
    det = AnomalyDetector()
    anomalies = _detect(det, "clean")
    types = _types(anomalies)
    # Clean'de yosun, pas, çatlak, kopma olmamalı.
    # Missing yanlışlıkla tetiklenebiliyorsa missing_aspect range'ini ayarla.
    assert AnomalyDetector.ALGAE not in types
    assert AnomalyDetector.RUST not in types
    assert AnomalyDetector.CRACK not in types
    assert AnomalyDetector.BREAK not in types
    assert AnomalyDetector.MISSING not in types


def test_no_detection_returns_empty():
    det = AnomalyDetector()
    # found=False ise hiç çalışmamalı
    assert det.detect(None, {"found": False}) == []
    assert det.detect(None, None) == []


def test_anomaly_bbox_within_frame():
    """bbox koordinatları frame içinde kalmalı (negatif veya taşkın değil)."""
    det = AnomalyDetector()
    gen = AnomalyDataset()
    for label in ("algae", "rust", "crack", "break", "missing"):
        frame, bbox = gen.make(label)
        detection = detection_from_frame(frame, bbox)
        anomalies = det.detect(frame, detection)
        h, w = frame.shape[:2]
        for a in anomalies:
            x, y, bw, bh = a["bbox"]
            assert 0 <= x and x + bw <= w + 1, f"{label}: bbox x taşkın"
            assert 0 <= y and y + bh <= h + 1, f"{label}: bbox y taşkın"
            assert bw >= 0 and bh >= 0, f"{label}: bbox negatif boyut"


def test_anomaly_payload_keys():
    """Her anomaly elemanı doğru anahtarları içermeli (ground_station JSON için)."""
    det = AnomalyDetector()
    anomalies = _detect(det, "algae")
    assert len(anomalies) > 0
    for a in anomalies:
        assert "type" in a
        assert "bbox" in a
        assert "confidence" in a
        assert "area_ratio" in a
        assert isinstance(a["bbox"], tuple)
        assert len(a["bbox"]) == 4


def test_break_frame_does_not_report_crack():
    """
    Break frame'inde sadece break raporlansın; kopuk uçların kenar pikselleri
    crack olarak yanlış sınıflanmamalı.
    """
    det = AnomalyDetector()
    types = _types(_detect(det, "break"))
    assert AnomalyDetector.BREAK in types
    assert AnomalyDetector.CRACK not in types


def test_rust_frame_does_not_report_break():
    """
    Rust pikselleri turuncu mask'i kesmesi mask'i fragmente eder ama bu
    fiziksel bir kopma değildir. Break false positive olmamalı.
    """
    det = AnomalyDetector()
    types = _types(_detect(det, "rust"))
    assert AnomalyDetector.RUST in types
    assert AnomalyDetector.BREAK not in types


def test_algae_frame_does_not_report_break():
    """Algae da rust gibi mask'i fragmente edebilir; break tetiklenmemeli."""
    det = AnomalyDetector()
    types = _types(_detect(det, "algae"))
    assert AnomalyDetector.ALGAE in types
    assert AnomalyDetector.BREAK not in types


def test_distractor_outside_bbox_does_not_trigger_break():
    """
    Boru bbox'ı dışında ayrı turuncu distractor varsa break TETİKLENMEMELİ.
    (Eski full-mask analizi bunu yanlışlıkla break sayıyordu.)
    """
    det = AnomalyDetector()
    gen = AnomalyDataset()
    frame, bbox = gen.make_clean_with_distractor()
    detection = detection_from_frame(frame, bbox)
    anomalies = det.detect(frame, detection)
    types = _types(anomalies)
    assert AnomalyDetector.BREAK not in types


def test_confidence_within_unit_range():
    """Tüm anomaly tipleri için confidence ∈ [0.0, 1.0]."""
    det = AnomalyDetector()
    gen = AnomalyDataset()
    for label in ("algae", "rust", "crack", "break", "missing"):
        frame, bbox = gen.make(label)
        detection = detection_from_frame(frame, bbox)
        for a in det.detect(frame, detection):
            assert 0.0 <= a["confidence"] <= 1.0, \
                f"{label}/{a['type']}: confidence {a['confidence']} aralık dışı"


def test_payload_is_json_safe():
    """
    Ground station numpy objesi gönderememeli — payload doğrudan json.dumps
    ile serialize olmalı (default=str fallback'siz).
    """
    import json
    det = AnomalyDetector()
    gen = AnomalyDataset()
    for label in ("algae", "rust", "crack", "break", "missing"):
        frame, bbox = gen.make(label)
        detection = detection_from_frame(frame, bbox)
        anomalies = det.detect(frame, detection)
        # main.py'daki dönüşümü taklit et (numpy temizliği)
        payload = [
            {
                "type": str(a["type"]),
                "bbox": [int(v) for v in a["bbox"]],
                "confidence": round(float(a["confidence"]), 3),
                "area_ratio": round(float(a["area_ratio"]), 3),
            }
            for a in anomalies
        ]
        json.dumps(payload)  # raise etmemeli


def test_overlay_empty_anomalies_does_not_crash():
    """draw_overlay anomalies=None / [] / eksik durumlarda hata vermemeli."""
    import numpy as np
    from debug_overlay import draw_overlay
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detection = {"found": False, "cx": 0, "cy": 0, "bbox": (0, 0, 0, 0)}
    action = {"state": "SEARCH", "message": "test"}
    # 3 senaryo: None, [], hiç verilmemiş
    draw_overlay(frame, detection, action, anomalies=None)
    draw_overlay(frame, detection, action, anomalies=[])
    draw_overlay(frame, detection, action)
