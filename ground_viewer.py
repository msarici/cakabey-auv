"""
ground_viewer.py — Kara İstasyonu UDP Telemetri Alıcı (Standalone)
Çakabey AUV | TEKNOCAK 2026

Kara tarafında çalışır. UDP soketinde dinler, gelen JSON paketlerini
ekrana basar. Paket sırasını seq ile takip edip kayıp tespit eder.

Kullanim:
    python ground_viewer.py --port 14651
    python ground_viewer.py --port 14651 --bind 0.0.0.0 --quiet
"""

import argparse
import json
import socket
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="Cakabey AUV Ground Viewer")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind IP (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=14651, help="UDP port")
    parser.add_argument("--quiet", action="store_true",
                        help="Sadece ozet bas, paket detayini gosterme")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    sock.settimeout(1.0)

    print(f"[ground_viewer] Dinleniyor: {args.bind}:{args.port}")
    print("Cikis: Ctrl+C")
    print("-" * 60)

    last_seq = -1
    total_packets = 0
    lost_packets = 0
    start_t = time.time()
    last_print_t = start_t

    try:
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue

            try:
                pkt = json.loads(data.decode("utf-8"))
            except Exception as e:
                print(f"[ground_viewer] Parse hatasi: {e}")
                continue

            total_packets += 1
            last_seq, lost_for_pkt = _process_one(pkt, addr, last_seq, quiet=args.quiet)
            lost_packets += lost_for_pkt

            # Her saniyede bir ozet bas
            now = time.time()
            if now - last_print_t >= 1.0:
                elapsed = now - start_t
                rate = total_packets / elapsed if elapsed > 0 else 0
                loss = lost_packets / max(total_packets + lost_packets, 1) * 100
                print(f"[stats] paket={total_packets} kayip={lost_packets} "
                      f"({loss:.1f}%) hiz={rate:.1f} Hz")
                last_print_t = now

    except KeyboardInterrupt:
        print("\n[ground_viewer] Kapatiliyor...")
    finally:
        sock.close()


def _process_one(pkt, addr, last_seq, quiet=False):
    """
    Tek paket için loss analizi + print. Loop'tan ayrı tutuldu ki testlenebilsin.
    Malformed paket (dict değil, seq int değil, eksik alan) ne pahasına olursa
    olsun raise etmemeli — kara istasyonu uzun süre çalışmalı.

    Returns: (new_last_seq, lost_count_for_this_packet)
    """
    # 1) pkt dict değilse seq/loss analizi yapma; sadece güvenli print.
    if not isinstance(pkt, dict):
        if not quiet:
            _print_packet(pkt, addr)
        return last_seq, 0

    # 2) seq int değilse (string, None, float, bool) loss tespiti yapma.
    #    bool int subclass'ı olduğu için açık ele al.
    seq = pkt.get("seq", -1)
    if isinstance(seq, bool) or not isinstance(seq, int):
        if not quiet:
            _print_packet(pkt, addr)
        return last_seq, 0

    # 3) Geçerli int seq: loss hesapla, last_seq güncelle.
    lost = 0
    if last_seq >= 0 and seq > last_seq + 1:
        lost = seq - last_seq - 1
        print(f"[ground_viewer] {lost} paket kayip (seq {last_seq}->{seq})")

    if not quiet:
        _print_packet(pkt, addr)

    return seq, lost


def _print_packet(pkt, addr):
    """
    Malformed paket gelirse crash etmesin. Kara istasyonu uzun süre çalışmalı,
    bozuk bir paket yüzünden döngüden düşmesin. Tüm alanlarda güvenli fallback.
    """
    if not isinstance(pkt, dict):
        print(f"[malformed] dict degil: {type(pkt).__name__}")
        return

    detection = pkt.get("detection") or {}
    sensor = pkt.get("sensor") or {}
    control = pkt.get("control") or {}
    if not isinstance(detection, dict):
        detection = {}
    if not isinstance(sensor, dict):
        sensor = {}
    if not isinstance(control, dict):
        control = {}

    seq = _fmt_int(pkt.get("seq"), "    -", width=6)
    state = _fmt_str(pkt.get("state"), "-", width=8)
    found = _fmt_int(detection.get("found", 0), "0", width=1)
    cx = _fmt_int(detection.get("cx"), "   -", width=4)
    cy = _fmt_int(detection.get("cy"), "   -", width=4)
    area = _fmt_int(detection.get("area"), "    -", width=5)
    voltage = _fmt_float(sensor.get("voltage"), "-", fmt="{:.1f}")
    yaw = _fmt_int(control.get("yaw_cmd"), "   -", width=4, sign=True)
    fwd_raw = control.get("forward_speed", control.get("fwd_cmd"))
    fwd = _fmt_int(fwd_raw, "   -", width=4, sign=True)
    fps = _fmt_float(pkt.get("fps"), "-", fmt="{:.0f}")
    dist = pkt.get("distance_cm")
    dist_str = _fmt_float(dist, "-", fmt="{:.1f}") + ("cm" if isinstance(dist, (int, float)) else "")
    anomalies = pkt.get("anomalies") or []
    n_anom = len(anomalies) if isinstance(anomalies, list) else 0

    print(f"#{seq} {state} found={found} "
          f"cx={cx} cy={cy} area={area} "
          f"V={voltage} yaw={yaw} fwd={fwd} "
          f"fps={fps} d={dist_str} anom={n_anom}")


def _fmt_int(value, fallback, width=0, sign=False):
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)):
        try:
            ivalue = int(value)
            spec = f"{'+' if sign else ''}{width}d"
            return format(ivalue, spec)
        except (ValueError, OverflowError):
            return fallback
    return fallback


def _fmt_str(value, fallback, width=0):
    s = str(value) if value is not None else fallback
    return s.ljust(width)[:max(width, len(s))] if width else s


def _fmt_float(value, fallback, fmt="{:.1f}"):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return fmt.format(float(value))
        except (ValueError, OverflowError):
            return fallback
    return fallback


if __name__ == "__main__":
    main()
