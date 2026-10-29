"""
safety.py — Güvenlik Kontrol Modülü
Çakabey AUV | TEKNOCAK 2026

Batarya kritik seviye, watchdog timeout ve sızıntı kontrolü.

Yapılandırılmış sızıntı sensörü arızaları acil durum olarak kilitlenir.
"""

import math
import time

try:
    import Jetson.GPIO as GPIO
    GPIO_OK = True
except (ImportError, RuntimeError, OSError):
    GPIO_OK = False


class SafetyMonitor:
    def __init__(
        self,
        vehicle,
        warn_voltage=13.0,
        critical_voltage=12.0,
        watchdog_timeout=2.0,
        leak_pin=None,
        leak_active_high=True,
    ):
        warn_voltage, critical_voltage, watchdog_timeout = map(
            float, (warn_voltage, critical_voltage, watchdog_timeout))
        if not all(math.isfinite(v) and v > 0 for v in
                   (warn_voltage, critical_voltage, watchdog_timeout)):
            raise ValueError("Safety thresholds must be positive and finite")
        if critical_voltage > warn_voltage:
            raise ValueError("critical_voltage must not exceed warn_voltage")
        self.vehicle = vehicle
        self.warn_voltage = warn_voltage
        self.critical_voltage = critical_voltage
        self.watchdog_timeout = watchdog_timeout
        self.leak_pin = leak_pin
        self.leak_active_high = leak_active_high

        self._leak_fault = None
        self._leak_setup_attempted = False
        self._leak_initialized = False
        self._leak_warned_once = False

        self._init_leak_sensor()

    def _init_leak_sensor(self):
        """
        Sızıntı sensörü için Jetson GPIO başlatma.

        Pin verilmemişse kontrol devre dışıdır; yapılandırılmış pin arızası kilitlenir.
        Jetson üzerinde gerçek sızıntı sensörü bağlandığında BCM pin numarası
        config.yaml > safety.leak_pin altında verilmeli.
        """
        if self.leak_pin is None:
            return

        if not GPIO_OK:
            self._leak_fault = "Sızıntı sensörü arızası: Jetson.GPIO kullanılamıyor"
            return

        try:
            GPIO.setmode(GPIO.BCM)
            pull = GPIO.PUD_DOWN if self.leak_active_high else GPIO.PUD_UP
            self._leak_setup_attempted = True
            GPIO.setup(self.leak_pin, GPIO.IN, pull_up_down=pull)
            self._leak_initialized = True
            print(f"[safety] Sızıntı sensörü pin {self.leak_pin} aktif.")
        except Exception as e:
            self._leak_fault = f"Sızıntı sensörü başlatma arızası: {e}"

    def check(self, sensor_data):
        """
        sensor_data: dict ya da None. None ise pil/heading/watchdog skip edilir
        ama sızıntı yine kontrol edilir (GPIO Pixhawk'tan bağımsız).

        timestamp: vehicle.read_sensors monotonic clock kullanır; bu fonksiyon
        da time.monotonic() ile karşılaştırır — sistem saati kaymalarına immün.
        """
        status = {
            "emergency": False,
            "reason": "",
            "warnings": [],
        }

        # Sızıntı önce kontrol — sensor None olsa bile çalışır.
        leak = self._check_leak()
        if self._leak_fault:
            status["emergency"] = True
            status["reason"] = self._leak_fault
            return status

        if leak:
            status["emergency"] = True
            status["reason"] = "Su kaçağı algılandı"
            return status

        if not self._leak_initialized and not self._leak_warned_once:
            status["warnings"].append("Sızıntı sensörü pasif - donanım entegrasyonu eksik")
            self._leak_warned_once = True

        if sensor_data is None:
            return status

        voltage = sensor_data.get("voltage", 0.0)
        timestamp = sensor_data.get("timestamp")

        if not isinstance(voltage, (int, float)) or not math.isfinite(voltage) or voltage <= 0:
            status["emergency"] = True
            status["reason"] = "Batarya verisi geçersiz"
            return status

        now = time.monotonic()
        for name, stamp in (("Sensör", timestamp),
                            ("Heartbeat", sensor_data.get("heartbeat_timestamp"))):
            if stamp is None:
                continue  # Preserve legacy timestamp-less monitor/test API.
            if (not isinstance(stamp, (int, float)) or not math.isfinite(stamp)
                    or stamp > now):
                status["emergency"] = True
                status["reason"] = f"{name} zaman damgası geçersiz"
                return status
            if name == "Heartbeat" and now - stamp > self.watchdog_timeout:
                status["emergency"] = True
                status["reason"] = "Heartbeat zaman aşımı"
                return status

        # Kritik batarya
        if voltage > 0 and voltage <= self.critical_voltage:
            status["emergency"] = True
            status["reason"] = f"Batarya kritik: {voltage:.1f}V"
            return status

        # Düşük batarya uyarısı
        if voltage > 0 and voltage <= self.warn_voltage:
            status["warnings"].append(f"Batarya düşük: {voltage:.1f}V")

        # Watchdog - sensör donmuşsa emergency. timestamp None ise atla
        # (test stub'ları için tolerans).
        if timestamp is not None and time.monotonic() - timestamp > self.watchdog_timeout:
            status["emergency"] = True
            status["reason"] = "Sensör zaman aşımı"
            return status

        return status

    def _check_leak(self):
        """
        Sızıntı sensörü okuma.

        Yapılandırılmamışsa False döner; okuma arızası kilitli acil durumdur.
        Aktif ise GPIO seviyesini okur:
        - leak_active_high=True: HIGH = sızıntı
        - leak_active_high=False: LOW = sızıntı
        """
        if not self._leak_initialized or self.leak_pin is None:
            return False

        try:
            level = GPIO.input(self.leak_pin)
            if level not in (GPIO.HIGH, GPIO.LOW):
                raise ValueError(f"Geçersiz GPIO seviyesi: {level!r}")
            if self.leak_active_high:
                return level == GPIO.HIGH
            else:
                return level == GPIO.LOW
        except Exception as e:
            self._leak_fault = f"Sızıntı sensörü okuma arızası: {e}"
            return False

    def cleanup(self):
        """
        GPIO kaynaklarını serbest bırak.
        Program kapanışında çağrılmalı.
        """
        if self._leak_setup_attempted and GPIO_OK:
            try:
                GPIO.cleanup(self.leak_pin)
            except Exception:
                pass