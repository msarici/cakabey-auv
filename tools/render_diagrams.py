"""
render_diagrams.py — DTR 6.3 için PNG diyagramları üretir.

Mermaid yerine matplotlib ile native render. Çıktılar:
    dtr_diagram_arch.png      - Sistem mimarisi (Görsel 1)
    dtr_diagram_fsm.png       - FSM durum geçiş (Görsel 2)
    dtr_diagram_pipeline.png  - Boru tespit pipeline (Görsel 3)
    dtr_diagram_anomaly.png   - Anomali pipeline (Görsel 4)
"""

import os

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
from matplotlib.lines import Line2D


PRIMARY = "#1F4E79"     # koyu mavi (kutu çerçeve)
ACCENT = "#2E75B6"      # orta mavi
LIGHT = "#D9E2F3"       # açık mavi (dolgu)
SOFT = "#F4F4F4"        # açık gri
GREEN = "#385723"
ORANGE = "#C55A11"
RED = "#C00000"
TEXT = "#222222"


def box(ax, x, y, w, h, text, *, fill=LIGHT, edge=PRIMARY, fontsize=9,
        bold=False, fontcolor=TEXT):
    """Yuvarlatılmış kutu."""
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        facecolor=fill, edgecolor=edge, linewidth=1.4,
    )
    ax.add_patch(rect)
    weight = "bold" if bold else "normal"
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=fontsize,
            color=fontcolor, weight=weight, wrap=True)


def arrow(ax, x1, y1, x2, y2, *, color=PRIMARY, style="-|>", lw=1.4,
          dashed=False, label=None, label_offset=(0, 0.1)):
    line_style = "dashed" if dashed else "solid"
    a = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style,
        mutation_scale=14,
        color=color, linewidth=lw,
        linestyle=line_style,
    )
    ax.add_patch(a)
    if label:
        mx = (x1 + x2) / 2 + label_offset[0]
        my = (y1 + y2) / 2 + label_offset[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=7.5,
                color=TEXT, style="italic")


def setup_ax(ax, title, xlim, ylim):
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=12, weight="bold", color=PRIMARY, pad=10)


# ============================================================
# 1) SİSTEM MİMARİSİ
# ============================================================

def render_architecture(out_path):
    fig, ax = plt.subplots(figsize=(13, 8))
    setup_ax(ax, "Çakabey AUV — Yazılım Mimarisi", (-0.5, 17.5), (-0.5, 11.5))

    # Sol: Kamera kaynakları
    ax.text(1.5, 10.7, "Kamera Katmanı", ha="center", weight="bold",
            fontsize=10, color=PRIMARY)
    box(ax, 0.2, 9, 2.6, 1, "CSI Kamera\n(nvarguscamerasrc)", fontsize=8)
    box(ax, 0.2, 7.7, 2.6, 1, "Webcam", fontsize=8)
    box(ax, 0.2, 6.4, 2.6, 1, "Sentetik Test\n(--sim)", fontsize=8)

    # Orta: Jetson grubu (büyük çerçeve)
    jx, jy, jw, jh = 3.5, 0.3, 9.5, 11
    jetson_outer = FancyBboxPatch(
        (jx, jy), jw, jh,
        boxstyle="round,pad=0.05,rounding_size=0.25",
        facecolor=SOFT, edgecolor=PRIMARY, linewidth=2.2,
    )
    ax.add_patch(jetson_outer)
    ax.text(jx + jw / 2, jy + jh - 0.3,
            "Üst Beyin — NVIDIA Jetson Orin Nano",
            ha="center", weight="bold", fontsize=11, color=PRIMARY)

    # Jetson içindeki modüller
    box(ax, 4.0, 8.7, 2.4, 1, "camera.py", fontsize=8.5, fill="white")
    box(ax, 6.6, 8.7, 2.4, 1, "pipe_detector.py\n(HSV+morfoloji+\nkontur)", fontsize=7.5, fill="white")
    box(ax, 9.2, 8.7, 2.4, 1, "anomaly_detector.py\n(5 sınıf, ROI)", fontsize=7.5, fill="white")

    box(ax, 4.0, 6.8, 2.4, 1, "fsm.py\n(SEARCH/APPROACH/\nTRACK/LOST)", fontsize=7.5, fill="white")
    box(ax, 6.6, 6.8, 2.4, 1, "pid_controller.py\n(yaw, anti-windup)", fontsize=7.5, fill="white")
    box(ax, 9.2, 6.8, 2.4, 1, "distance.py\n(pinhole/lazer)", fontsize=7.5, fill="white")

    box(ax, 4.0, 4.9, 2.4, 1, "safety.py\n(volt/watchdog/\nleak)", fontsize=7.5, fill="white")
    box(ax, 6.6, 4.9, 2.4, 1, "main.py\n(ANA DÖNGÜ)", fontsize=8, fill=LIGHT, bold=True)
    box(ax, 9.2, 4.9, 2.4, 1, "vehicle.py\n(MAVLink)", fontsize=8, fill="white")

    box(ax, 4.0, 3.0, 2.4, 1, "telemetry_logger.py\n(CSV)", fontsize=7.5, fill="white")
    box(ax, 6.6, 3.0, 2.4, 1, "ground_station.py\n(UDP/JSON 10 Hz)", fontsize=7.5, fill="white")
    box(ax, 9.2, 3.0, 2.4, 1, "abc_optimizer.py\n+ tune_hsv/pid", fontsize=7.5, fill="white")

    # Bağlantılar (kamera → camera.py → main)
    arrow(ax, 2.8, 9.5, 4.0, 9.2, color=ACCENT)
    arrow(ax, 2.8, 8.2, 4.0, 9.0, color=ACCENT)
    arrow(ax, 2.8, 6.9, 4.0, 8.8, color=ACCENT)

    # Jetson içi akış: camera → main, detect → main, fsm/pid → main
    arrow(ax, 5.2, 8.7, 6.6, 5.9, color=ACCENT)        # camera.py → main
    arrow(ax, 7.8, 8.7, 7.8, 7.8, color=ACCENT)        # detector → fsm
    arrow(ax, 7.8, 6.8, 7.8, 5.9, color=ACCENT)        # fsm → pid → main
    arrow(ax, 5.2, 4.9, 6.6, 5.4, color=ACCENT)        # safety → main
    arrow(ax, 9.2, 5.4, 8.0, 5.4, color=ACCENT)        # main → vehicle (sol-sağ ok)
    arrow(ax, 7.0, 4.9, 6.0, 4.0, color=ACCENT)        # main → telemetry
    arrow(ax, 7.8, 4.9, 7.8, 4.0, color=ACCENT)        # main → ground

    # Sağ: Pixhawk grubu
    px, py, pw, ph = 13.8, 4.5, 3.3, 5.0
    pix_outer = FancyBboxPatch(
        (px, py), pw, ph,
        boxstyle="round,pad=0.05,rounding_size=0.25",
        facecolor="#FFF4E6", edgecolor=ORANGE, linewidth=2.2,
    )
    ax.add_patch(pix_outer)
    ax.text(px + pw / 2, py + ph - 0.3, "Alt Beyin\nPixhawk 2.4.8",
            ha="center", weight="bold", fontsize=10, color=ORANGE)

    box(ax, 14.0, 7.5, 3.0, 1.0, "MAVLink\nRC_CHANNELS_OVERRIDE",
        fontsize=7.5, fill="white", edge=ORANGE)
    box(ax, 14.0, 6.2, 3.0, 1.0, "6× DEGZ Blu 30A ESC",
        fontsize=8, fill="white", edge=ORANGE)
    box(ax, 14.0, 4.9, 3.0, 1.1, "4× Mitras yatay 45°\n2× Ultras dikey",
        fontsize=8, fill="white", edge=ORANGE)

    # Jetson → Pixhawk arrow
    arrow(ax, 11.6, 5.4, 14.0, 8.0, color=ORANGE, lw=2,
          label="RC PWM", label_offset=(0.3, -0.4))
    arrow(ax, 15.5, 7.5, 15.5, 7.2, color=ORANGE)
    arrow(ax, 15.5, 6.2, 15.5, 6.0, color=ORANGE)

    # Kara istasyonu (alt-sağ)
    box(ax, 14.0, 1.5, 3.0, 1.4,
        "Kara İstasyonu\nCAT6 / UDP\n192.168.2.1:14651",
        fontsize=8, fill="#E8F5E9", edge=GREEN)
    arrow(ax, 9.0, 3.0, 14.0, 2.2, color=GREEN, dashed=True,
          label="UDP/JSON", label_offset=(0, 0.3))

    plt.tight_layout()
    plt.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[diagram] arch -> {out_path}")


# ============================================================
# 2) FSM DURUM GEÇİŞ
# ============================================================

def render_fsm(out_path):
    fig, ax = plt.subplots(figsize=(11, 7))
    setup_ax(ax, "FSM — Durum Geçiş Diyagramı", (-0.5, 13.5), (-0.5, 7.5))

    # Durum daireleri (x, y, label, açıklama)
    states = {
        "SEARCH":   (1.7, 5.5, "Yaw arama (150)\nForward = 0"),
        "APPROACH": (5.5, 5.5, "Yaw PID açık\nForward = 200"),
        "TRACK":    (9.5, 5.5, "Yaw PID açık\nArea büyürse ×0.6"),
        "LOST":     (5.5, 1.7, "Yaw arama\nForward = 0"),
    }

    state_colors = {
        "SEARCH": "#FFF3CD",
        "APPROACH": "#D9E2F3",
        "TRACK": "#D5E8D4",
        "LOST": "#F8CECC",
    }

    for name, (x, y, desc) in states.items():
        circ = Circle((x, y), 1.05, facecolor=state_colors[name],
                      edgecolor=PRIMARY, linewidth=2.2)
        ax.add_patch(circ)
        ax.text(x, y + 0.15, name, ha="center", va="center",
                weight="bold", fontsize=10, color=PRIMARY)
        ax.text(x, y - 0.45, desc, ha="center", va="center",
                fontsize=7, color=TEXT)

    # Geçişler (from, to, label, curve dir)
    # Helper: küçük ofset ile dairelerin kenarına ok
    def edge_arrow(s_from, s_to, label, side="top", curve=0.0):
        x1, y1, _ = states[s_from]
        x2, y2, _ = states[s_to]
        # Yön vektörü
        import math
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy)
        ux, uy = dx / d, dy / d
        r = 1.1
        sx, sy = x1 + ux * r, y1 + uy * r
        ex, ey = x2 - ux * r, y2 - uy * r
        a = FancyArrowPatch(
            (sx, sy), (ex, ey),
            connectionstyle=f"arc3,rad={curve}",
            arrowstyle="-|>", mutation_scale=14,
            color=PRIMARY, linewidth=1.5,
        )
        ax.add_patch(a)
        # Label konum
        midx = (sx + ex) / 2
        midy = (sy + ey) / 2
        # Curve normal vektörü
        nx, ny = -uy, ux
        midx += nx * curve * d * 0.5
        midy += ny * curve * d * 0.5
        ax.text(midx, midy, label, ha="center", va="center",
                fontsize=7.5, color=ACCENT, style="italic",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                          edgecolor="none", alpha=0.9))

    edge_arrow("SEARCH",   "APPROACH", "3 ardışık frame\nboru görüldü", curve=0.0)
    edge_arrow("APPROACH", "TRACK",    "found ∧\narea ≥ 2000 px", curve=0.0)
    edge_arrow("APPROACH", "LOST",     "30 frame yok", curve=-0.3)
    edge_arrow("TRACK",    "LOST",     "30 frame yok", curve=-0.2)
    edge_arrow("LOST",     "APPROACH", "tekrar görüldü", curve=-0.3)
    edge_arrow("LOST",     "SEARCH",   "30 frame daha\narama başarısız", curve=-0.2)

    # Başlangıç oku (giriş)
    a = FancyArrowPatch((0.0, 5.5), (0.55, 5.5), arrowstyle="-|>",
                        mutation_scale=14, color=GREEN, linewidth=2)
    ax.add_patch(a)
    ax.text(0.0, 5.95, "başlangıç", ha="center", fontsize=8,
            color=GREEN, weight="bold")

    plt.tight_layout()
    plt.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[diagram] fsm -> {out_path}")


# ============================================================
# 3) BORU TESPİT PIPELINE
# ============================================================

def render_pipeline(out_path):
    fig, ax = plt.subplots(figsize=(14, 4))
    setup_ax(ax, "Boru Tespit İşlem Hattı", (-0.5, 21), (-0.5, 4))

    steps = [
        (0.0, "BGR Frame\n640×480"),
        (2.6, "Gaussian Blur\n5×5"),
        (5.2, "BGR → HSV\ncvtColor"),
        (7.8, "cv2.inRange\nH 10-25\nS 100-255\nV 80-255"),
        (10.4, "MORPH_OPEN\n5×5"),
        (13.0, "MORPH_CLOSE\n5×5"),
        (15.6, "findContours\nen büyük (≥500 px)"),
        (18.2, "boundingRect\nmoments → cx,cy\nerror_x = cx - W/2"),
    ]

    bw, bh = 2.3, 1.3
    by = 1.5
    for i, (x, text) in enumerate(steps):
        fill = LIGHT if i in (3, 6, 7) else "white"
        bold = i in (3, 7)
        box(ax, x, by, bw, bh, text, fill=fill, fontsize=7.7, bold=bold)
        if i < len(steps) - 1:
            arrow(ax, x + bw, by + bh / 2, x + 2.6, by + bh / 2, color=ACCENT)

    # Çıktı kutusu
    ax.text(20.5, 0.7, "Çıktı:\n{found, cx, cy, bbox, area, error_x, mask}",
            ha="right", fontsize=8, color=PRIMARY, weight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor=SOFT,
                      edgecolor=PRIMARY))

    plt.tight_layout()
    plt.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[diagram] pipeline -> {out_path}")


# ============================================================
# 4) ANOMALİ PIPELINE
# ============================================================

def render_anomaly(out_path):
    fig, ax = plt.subplots(figsize=(13, 9))
    setup_ax(ax, "Anomali Tespit Pipeline'ı (ROI Tabanlı)",
             (-0.5, 16), (-0.5, 11))

    # Giriş
    box(ax, 5.5, 9.5, 4.0, 1.0,
        "PipeDetector çıktısı\n(found, bbox, mask)",
        fill=LIGHT, fontsize=8.5, bold=True)

    # found check
    arrow(ax, 7.5, 9.5, 7.5, 8.7, color=ACCENT)
    box(ax, 6.5, 7.7, 2.0, 1.0, "found?", fill="#FFF3CD",
        fontsize=9, bold=True)

    # Hayır → boş
    arrow(ax, 6.5, 8.2, 4.5, 8.2, color=RED)
    ax.text(5.5, 8.4, "Hayır", color=RED, ha="center", fontsize=8)
    box(ax, 1.8, 7.7, 2.7, 1.0, "boş liste döndür",
        fill="#F8CECC", fontsize=8.5)

    # Evet → ROI
    arrow(ax, 7.5, 7.7, 7.5, 6.9, color=ACCENT)
    ax.text(8.0, 7.3, "Evet", color=GREEN, fontsize=8)
    box(ax, 5.5, 5.9, 4.0, 1.0,
        "ROI = frame[bbox] ∩ mask[bbox]",
        fill=LIGHT, fontsize=8.5)

    # Üç paralel kol: yapısal, renk, çatlak
    arrow(ax, 6.5, 5.9, 3.5, 4.8, color=ACCENT)
    arrow(ax, 7.5, 5.9, 7.5, 4.8, color=ACCENT)
    arrow(ax, 8.5, 5.9, 11.5, 4.8, color=ACCENT)

    # YAPISAL: break/missing
    box(ax, 1.5, 3.8, 4.0, 1.0,
        "MORPH_CLOSE 49×9\n(yatay-eğilimli)",
        fill="white", fontsize=8)
    arrow(ax, 3.5, 3.8, 3.5, 3.3, color=ACCENT)
    box(ax, 1.5, 2.3, 4.0, 1.0,
        "≥2 kontur → BREAK\nveya aspect <3 → MISSING",
        fill="#FFE4B5", fontsize=8, bold=True)

    # RENK: algae/rust
    box(ax, 5.5, 3.8, 4.0, 1.0,
        "ROI HSV maskeleri",
        fill="white", fontsize=8)
    arrow(ax, 7.5, 3.8, 7.5, 3.3, color=ACCENT)
    box(ax, 5.5, 2.3, 4.0, 1.0,
        "yeşil ≥5% → ALGAE\npas ≥3% → RUST",
        fill="#D5E8D4", fontsize=8, bold=True)

    # ÇATLAK
    box(ax, 9.5, 3.8, 4.0, 1.0,
        "Canny + HoughLinesP",
        fill="white", fontsize=8)
    arrow(ax, 11.5, 3.8, 11.5, 3.3, color=ACCENT)
    box(ax, 9.5, 2.3, 4.0, 1.0,
        "≥1 çizgi → CRACK\n(BREAK varsa bastır)",
        fill="#F8CECC", fontsize=8, bold=True)

    # Birleşim
    arrow(ax, 3.5, 2.3, 7.5, 1.4, color=ACCENT)
    arrow(ax, 7.5, 2.3, 7.5, 1.4, color=ACCENT)
    arrow(ax, 11.5, 2.3, 7.5, 1.4, color=ACCENT)

    box(ax, 4.0, 0.4, 7.0, 1.0,
        "Anomali listesi:\n[{type, bbox, confidence, area_ratio}, ...]",
        fill=LIGHT, fontsize=9, bold=True)

    plt.tight_layout()
    plt.savefig(out_path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[diagram] anomaly -> {out_path}")


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.dirname(out_dir)  # repo root
    render_architecture(os.path.join(out_dir, "dtr_diagram_arch.png"))
    render_fsm(os.path.join(out_dir, "dtr_diagram_fsm.png"))
    render_pipeline(os.path.join(out_dir, "dtr_diagram_pipeline.png"))
    render_anomaly(os.path.join(out_dir, "dtr_diagram_anomaly.png"))


if __name__ == "__main__":
    main()
