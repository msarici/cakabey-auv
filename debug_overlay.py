"""
debug_overlay.py — Görsel Üstüne Bilgi Yazdırma
Çakabey AUV | TEKNOCAK 2026
"""

import cv2


# Anomaly tipi -> bbox rengi (BGR). Görsel ayırt edicilik için seçildi.
ANOMALY_COLORS = {
    "algae":   (0, 220, 0),     # parlak yesil
    "rust":    (0, 80, 200),    # turuncu/kahverengi
    "crack":   (0, 0, 255),     # kirmizi
    "break":   (0, 0, 180),     # koyu kirmizi
    "missing": (0, 165, 255),   # turuncu uyari
}


def draw_overlay(frame, detection, action, sensor=None, fps=0.0, distance_cm=None,
                 yaw_cmd=0, fwd_cmd=0, anomalies=None):
    view = frame.copy()
    h, w = view.shape[:2]
    mx, my = w // 2, h // 2

    cv2.line(view, (mx - 15, my), (mx + 15, my), (0, 255, 0), 2)
    cv2.line(view, (mx, my - 15), (mx, my + 15), (0, 255, 0), 2)

    if detection.get("found", False):
        cx = detection.get("cx", 0)
        cy = detection.get("cy", 0)
        bx, by, bw, bh = detection.get("bbox", (0, 0, 0, 0))

        cv2.circle(view, (cx, cy), 7, (0, 0, 255), -1)
        cv2.line(view, (mx, my), (cx, cy), (255, 120, 0), 2)
        cv2.rectangle(view, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)

    # Anomaly bbox'lari
    if anomalies:
        for a in anomalies:
            atype = a.get("type", "")
            bbox = a.get("bbox", (0, 0, 0, 0))
            ax, ay, aw, ah = bbox
            color = ANOMALY_COLORS.get(atype, (200, 200, 200))
            cv2.rectangle(view, (ax, ay), (ax + aw, ay + ah), color, 2)
            label = f"{atype} {a.get('confidence', 0):.2f}"
            cv2.putText(view, label, (ax, max(0, ay - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    state = action.get("state", "-")
    color = {
        "SEARCH": (255, 255, 255),
        "APPROACH": (0, 255, 255),
        "TRACK": (0, 255, 0),
        "LOST": (0, 0, 255),
    }.get(state, (200, 200, 200))

    lines = [
        f"FPS: {fps:.0f}",
        f"State: {state}",
        f"YAW: {yaw_cmd:+d}  FWD: {fwd_cmd:+d}",
        action.get("message", ""),
    ]

    if sensor is not None:
        lines.insert(3, f"Bat: {sensor.get('voltage', 0):.1f}V")

    if distance_cm is not None:
        lines.append(f"Mesafe: {distance_cm:.1f} cm")

    if anomalies:
        types_seen = sorted({a.get("type", "?") for a in anomalies})
        lines.append("Anomaly: " + ", ".join(types_seen))

    for i, text in enumerate(lines):
        cv2.putText(view, text, (10, 22 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    return view