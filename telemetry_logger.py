"""
telemetry_logger.py — CSV Telemetri Kaydı
Çakabey AUV | TEKNOCAK 2026

Her frame için tek satır CSV yazar.
Disk I/O'yu azaltmak için flush her satırda değil,
flush_interval frame'de bir yapılır.
Kapanışta her durumda son flush garantilenir.
"""

import csv
import os
import time


class TelemetryLogger:
    def __init__(self, directory="logs", enabled=True, flush_interval=30):
        self.directory = directory
        self.enabled = enabled
        self.flush_interval = max(1, int(flush_interval))

        self.file = None
        self.writer = None
        self._rows_since_flush = 0

    def start(self):
        if not self.enabled:
            return

        os.makedirs(self.directory, exist_ok=True)
        # Aynı saniyede başlayan iki run birbirini ezmesin: çakışma varsa suffix ekle
        base = time.strftime("telemetry_%Y%m%d_%H%M%S")
        path = os.path.join(self.directory, base + ".csv")
        suffix = 1
        while os.path.exists(path):
            path = os.path.join(self.directory, f"{base}_{suffix}.csv")
            suffix += 1

        self.file = open(path, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        self.writer.writerow([
            "time",
            "state",
            "found",
            "cx",
            "cy",
            "area",
            "yaw_cmd",
            "fwd_cmd",
            "voltage",
            "fps",
            "distance_cm",
        ])
        # header'ı hemen flush et ki dosya boş kalmasın
        self.file.flush()
        self._rows_since_flush = 0

    def log(self, action, detection, sensor, yaw_cmd, fwd_cmd, fps, distance_cm=None):
        if not self.enabled or self.writer is None:
            return

        self.writer.writerow([
            time.time(),
            action.get("state", ""),
            int(detection.get("found", False)),
            detection.get("cx", 0),
            detection.get("cy", 0),
            detection.get("area", 0),
            yaw_cmd,
            fwd_cmd,
            0 if sensor is None else sensor.get("voltage", 0),
            round(fps, 2),
            "" if distance_cm is None else round(distance_cm, 2),
        ])

        self._rows_since_flush += 1
        if self._rows_since_flush >= self.flush_interval:
            self.file.flush()
            self._rows_since_flush = 0

    def close(self):
        if self.file is not None:
            try:
                # son satırların kaybolmaması için kapanışta zorla flush
                self.file.flush()
            except Exception:
                pass
            self.file.close()
            self.file = None
            self.writer = None
            self._rows_since_flush = 0