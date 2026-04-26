"""
debug_overlay.py — Görsel Üstüne Bilgi Yazdırma
Çakabey AUV | TEKNOCAK 2026
"""

import cv2


def draw_overlay(frame, detection, action, sensor=None, fps=0.0, distance_cm=None, yaw_cmd=0, fwd_cmd=0):
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

    for i, text in enumerate(lines):
        cv2.putText(view, text, (10, 22 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    return view