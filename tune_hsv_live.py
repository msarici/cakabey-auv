"""
tune_hsv_live.py — Canlı HSV Trackbar Tuner
Çakabey AUV | TEKNOCAK 2026

Kameradan canlı görüntü + 6 trackbar (H/S/V min/max).
Boruyu kameraya tutup mask'ta sadece borunun beyaz kaldığı değerleri bulursun;
sonra çıkan sayıları config.yaml > detector altına yapıştırırsın.

Kullanım:
    python tune_hsv_live.py --source webcam        # laptop testi
    python tune_hsv_live.py --source csi           # Jetson CSI kamera
    python tune_hsv_live.py --source test          # sentetik turuncu boru

Kontroller:
    s : o anki H/S/V değerlerini config.yaml formatında konsola bas
    q : çıkış
"""

import argparse
import sys

import cv2
import numpy as np

from camera import Camera


def _noop(_value):
    pass


def _print_yaml(h_min, h_max, s_min, s_max, v_min, v_max):
    print()
    print("# --- config.yaml > detector altina kopyala ---")
    print("detector:")
    print(f"  h_min: {h_min}")
    print(f"  h_max: {h_max}")
    print(f"  s_min: {s_min}")
    print(f"  s_max: {s_max}")
    print(f"  v_min: {v_min}")
    print(f"  v_max: {v_max}")
    print("# ---------------------------------------------")
    print()


def main():
    parser = argparse.ArgumentParser(description="Canli HSV trackbar tuner")
    parser.add_argument("--source", default="webcam",
                        choices=["csi", "webcam", "test"],
                        help="Kamera kaynagi (default: webcam)")
    parser.add_argument("--device-id", type=int, default=0,
                        help="Webcam device id (default: 0)")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    # Baslangic degerleri — config.yaml'daki guncel ABC sonucuyla ayni
    parser.add_argument("--h-min", type=int, default=9)
    parser.add_argument("--h-max", type=int, default=18)
    parser.add_argument("--s-min", type=int, default=152)
    parser.add_argument("--s-max", type=int, default=255)
    parser.add_argument("--v-min", type=int, default=114)
    parser.add_argument("--v-max", type=int, default=255)
    args = parser.parse_args()

    cam = Camera(
        source=args.source,
        device_id=args.device_id,
        width=args.width,
        height=args.height,
        fps=args.fps,
    )
    if not cam.open():
        print("[ERROR] Kamera acilamadi.", file=sys.stderr)
        return 1

    win = "HSV Tuner"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 600, 320)

    # H 0-179 (OpenCV), S/V 0-255
    cv2.createTrackbar("H_min", win, args.h_min, 179, _noop)
    cv2.createTrackbar("H_max", win, args.h_max, 179, _noop)
    cv2.createTrackbar("S_min", win, args.s_min, 255, _noop)
    cv2.createTrackbar("S_max", win, args.s_max, 255, _noop)
    cv2.createTrackbar("V_min", win, args.v_min, 255, _noop)
    cv2.createTrackbar("V_max", win, args.v_max, 255, _noop)

    print("[INFO] s: degerleri yazdir | q: cikis")

    while True:
        frame = cam.read()
        if frame is None:
            # CSI/webcam ilk frame'leri kacirabilir, donmeden bekle
            if cv2.waitKey(10) & 0xFF == ord("q"):
                break
            continue

        h_min = cv2.getTrackbarPos("H_min", win)
        h_max = cv2.getTrackbarPos("H_max", win)
        s_min = cv2.getTrackbarPos("S_min", win)
        s_max = cv2.getTrackbarPos("S_max", win)
        v_min = cv2.getTrackbarPos("V_min", win)
        v_max = cv2.getTrackbarPos("V_max", win)

        blur = cv2.GaussianBlur(frame, (5, 5), 0)
        hsv = cv2.cvtColor(blur, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            np.array([h_min, s_min, v_min], dtype=np.uint8),
            np.array([h_max, s_max, v_max], dtype=np.uint8),
        )
        result = cv2.bitwise_and(frame, frame, mask=mask)

        cv2.imshow("Camera", frame)
        cv2.imshow("Mask", mask)
        cv2.imshow("Result", result)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            _print_yaml(h_min, h_max, s_min, s_max, v_min, v_max)

    # Son degerleri otomatik bas
    h_min = cv2.getTrackbarPos("H_min", win)
    h_max = cv2.getTrackbarPos("H_max", win)
    s_min = cv2.getTrackbarPos("S_min", win)
    s_max = cv2.getTrackbarPos("S_max", win)
    v_min = cv2.getTrackbarPos("V_min", win)
    v_max = cv2.getTrackbarPos("V_max", win)
    print("[INFO] Cikis - son degerler:")
    _print_yaml(h_min, h_max, s_min, s_max, v_min, v_max)

    cam.close()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
