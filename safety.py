"""
safety.py — Güvenlik Kontrol Modülü
Çakabey AUV | TEKNOCAK 2026

Batarya kritik seviye, watchdog timeout ve sızıntı kontrolü.

Sızıntı kontrolü şu an PASIF (placeholder).
Donanım entegrasyonu için aşağıdaki TODO'ya bakın.
"""

import time

try:
    import Jetson.GPIO as GPIO
    GPIO_OK = True
except ImportError:
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
        self.vehicle = vehicle
        self.warn_voltage = warn_voltage
        self.critical_voltage = critical_voltage
        self.watchdog_timeout = watchdog_timeout
        self.leak_pin = leak_pin
        self.leak_active_high = leak_active_high

        self._leak_initialized = False
        self._leak_warned_once = False

        self._init_leak_sensor()

    def _init_leak_sensor(self):
        """
        Sızıntı sensörü için Jetson GPIO başlatma.

        Donanım yoksa veya pin verilmemişse pasif placeholder olarak çalışır.
        Jetson üzerinde gerçek sızıntı sensörü bağlandığında BCM pin numarası
        config.yaml > safety.leak_pin altında verilmeli.
        """
        if self.leak_pin is None:
            return

        if not GPIO_OK:
            print("[safety] Jetson.GPIO modülü yok. Sızıntı sensörü pasif.")
            return

        try:
            GPIO.setmode(GPIO.BCM)
            pull = GPIO.PUD_DOWN if self.leak_active_high else GPIO.PUD_UP
            GPIO.setup(self.leak_pin, GPIO.IN, pull_up_down=pull)
            self._leak_initialized = True
            print(f"[safety] Sızıntı sensörü pin {self.leak_pin} aktif.")
        except Exception as e:
            print(f"[safety] Sızıntı sensörü başlatılamadı: {e}")

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
        if self._check_leak():
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

        Aktif değilse her zaman False döner (güvenli varsayım: sızıntı yok).
        Aktif ise GPIO seviyesini okur:
        - leak_active_high=True: HIGH = sızıntı
        - leak_active_high=False: LOW = sızıntı
        """
        if not self._leak_initialized or self.leak_pin is None:
            return False

        try:
            level = GPIO.input(self.leak_pin)
            if self.leak_active_high:
                return level == GPIO.HIGH
            else:
                return level == GPIO.LOW
        except Exception as e:
            print(f"[safety] Sızıntı okuma hatası: {e}")
            return False

    def cleanup(self):
        """
        GPIO kaynaklarını serbest bırak.
        Program kapanışında çağrılmalı.
        """
        if self._leak_initialized and GPIO_OK:
            try:
                GPIO.cleanup(self.leak_pin)
            except Exception:
                pass