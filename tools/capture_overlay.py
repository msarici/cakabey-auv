"""
capture_overlay.py — DTR için debug overlay ekran görüntüsü üretir.

Sentetik bir frame üzerinde tüm pipeline'ı (tespit + anomali + FSM + PID)
çalıştırır ve draw_overlay çıktısını PNG olarak kaydeder. DTR rapor
görselleri (Görsel 5) için kullanılır.

Kullanım:
    python tools/capture_overlay.py --scenario track --out track.png
    python tools/capture_overlay.py --scenario algae --out algae.png
    python tools/capture_overlay.py --scenario all --out-prefix dtr_overlay
"""

import argparse
import os
import sys

# Repository root'u sys.path'e ekle ki "from camera import Camera" çalışsın
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import cv2

from anomaly_detector import AnomalyDetector
from debug_overlay import draw_overlay
from evaluator_anomaly import AnomalyDataset, detection_from_frame
from fsm import FSM
from pid_controller import PIDController
from pipe_detector import PipeDetector


SCENARIOS = ("clean", "algae", "rust", "crack", "break", "missing", "track")


def render(scenario, out_path):
    """Tek bir senaryo için overlay PNG üret."""
    detector = PipeDetector()
    anomaly_detector = AnomalyDetector()
    pid = PIDController(kp=1.97, ki=5.0, kd=0.29, output_min=-400, output_max=400,
                        integral_limit=200)

    if scenario == "track":
        # Saf takip görseli — anomaly yok, FSM TRACK durumunda
        gen = AnomalyDataset()
        frame, _ = gen.make("clean")
        detection = detector.detect(frame)
        anomalies = []
        state = FSM.TRACK
        msg = "Boru takip ediliyor"
        fwd_cmd = 200
    else:
        # Anomali senaryoları: GT bbox kullan ki break gibi parçalı durumlarda
        # ROI tüm boru aralığını kapsasın. Detector bazı senaryolarda yalnızca
        # bir parçayı yakalar; bu, anomali görselinin amacını bozar.
        gen = AnomalyDataset()
        frame, gt_bbox = gen.make(scenario)
        detection = detection_from_frame(frame, gt_bbox)
        anomalies = anomaly_detector.detect(frame, detection)
        state = FSM.TRACK
        msg = f"Anomali ornek: {scenario}"
        fwd_cmd = 200

    # PID yaw_cmd hesabı (gerçekçi görünüm)
    error_x = detection.get("error_x", 0)
    yaw_cmd = int(pid.compute(error_x))

    action = {"state": state, "message": msg}
    sensor = {"voltage": 15.4, "heading": 67}

    # Mesafe (pinhole)
    bw = detection.get("width", 0)
    distance_cm = (20.0 * 500.0) / bw if bw > 0 else None

    view = draw_overlay(
        frame=frame,
        detection=detection,
        action=action,
        sensor=sensor,
        fps=30.0,
        distance_cm=distance_cm,
        yaw_cmd=yaw_cmd,
        fwd_cmd=fwd_cmd,
        anomalies=anomalies,
    )

    cv2.imwrite(out_path, view)
    n_anom = len(anomalies)
    print(f"[capture] {scenario:>8s} -> {out_path}  (anomaly count: {n_anom})")


def main():
    parser = argparse.ArgumentParser(description="DTR overlay ekran görüntüsü üretir")
    parser.add_argument("--scenario", choices=SCENARIOS + ("all",), default="track")
    parser.add_argument("--out", default=None,
                        help="Tek senaryo için çıkış dosyası (--scenario all hariç)")
    parser.add_argument("--out-prefix", default="dtr_overlay",
                        help="--scenario all için dosya prefix'i")
    args = parser.parse_args()

    if args.scenario == "all":
        for s in SCENARIOS:
            out = f"{args.out_prefix}_{s}.png"
            render(s, out)
    else:
        out = args.out or f"{args.out_prefix}_{args.scenario}.png"
        render(args.scenario, out)


if __name__ == "__main__":
    main()
