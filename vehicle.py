"""
vehicle.py — Araç Arayüzü
Çakabey AUV | TEKNOCAK 2026

Gerçek Pixhawk varsa MAVLink ile konuşur.
Yoksa simülasyon modunda çalışır.

read_sensors için cache pattern:
MAVLink mesajları her frame gelmeyebilir (blocking=False).
Son geçerli değer saklanır, yeni mesaj gelene kadar cache'den döner.
Bu sayede tek bir frame kaybı sahte sıfır değer üretmez.
"""

import time

try:
    from pymavlink import mavutil
    MAVLINK_OK = True
except ImportError:
    MAVLINK_OK = False


class Vehicle:
    def __init__(self, connection="/dev/ttyACM0", baudrate=115200, heartbeat_timeout=3.0,
                 flight_mode="MANUAL", yaw_channel=4, forward_channel=5,
                 vertical_channel=3,
                 pwm_base=1500, pwm_min=1100, pwm_max=1900,
                 yaw_reverse=False, forward_reverse=False, vertical_reverse=False,
                 allow_sim_fallback=False):
        """
        flight_mode: ArduSub için tipik seçenekler MANUAL / STABILIZE / ALT_HOLD.
        yaw_channel/forward_channel/vertical_channel: ArduSub RCMAP_* parametreleri ile
            uyumlu olmalı. Mission Planner / QGC'de doğrula.
            Default ArduSub mapping: yaw=4, forward=5, vertical=3 (RCMAP_THROTTLE).
        *_reverse: kanal yonu ters cikiyorsa True yap — PWM offset'ini negate eder.
            Suya girmeden once mutlaka tek tek dogrula (havada test, her motor sirayla).
        pwm_base/min/max: motor PWM aralığı (1100-1900 us, neutral 1500).
        allow_sim_fallback: Pixhawk bağlantısı kurulamazsa sim moduna geçmesine izin
            verir. Production'da False (görev güvenliği). Geliştirme'de True.
        """
        yaw_channel = int(yaw_channel)
        forward_channel = int(forward_channel)
        vertical_channel = int(vertical_channel)
        for name, val in (("yaw_channel", yaw_channel),
                          ("forward_channel", forward_channel),
                          ("vertical_channel", vertical_channel)):
            if not (1 <= val <= 8):
                raise ValueError(f"{name} 1..8 aralığında olmalı, alındı: {val}")

        # Kanal carpismasi olursa motor double-write riski (RC override son yazani
        # uygular ama davranis tahmin edilemez); ayri kanallarda olmali.
        channels = {yaw_channel, forward_channel, vertical_channel}
        if len(channels) != 3:
            raise ValueError(
                f"yaw/forward/vertical kanallari ayri olmali, alindi: "
                f"yaw={yaw_channel}, forward={forward_channel}, vertical={vertical_channel}"
            )

        if not (pwm_min < pwm_base < pwm_max):
            raise ValueError(
                f"pwm_min < pwm_base < pwm_max olmalı, alındı: "
                f"min={pwm_min} base={pwm_base} max={pwm_max}"
            )

        self.connection = connection
        self.baudrate = baudrate
        self.heartbeat_timeout = heartbeat_timeout
        self.flight_mode = flight_mode
        self.yaw_channel = yaw_channel
        self.forward_channel = forward_channel
        self.vertical_channel = vertical_channel
        self.pwm_base = pwm_base
        self.pwm_min = pwm_min
        self.pwm_max = pwm_max
        self.yaw_reverse = bool(yaw_reverse)
        self.forward_reverse = bool(forward_reverse)
        self.vertical_reverse = bool(vertical_reverse)
        self.allow_sim_fallback = allow_sim_fallback

        self.master = None
        self.sim_mode = True
        self.armed = False
        self.last_rc = {"yaw": 0, "forward": 0, "vertical": 0}
        self._sim_voltage = 16.0

        # Sensör cache - en son geçerli değerler
        self._cached_voltage = None
        self._cached_heading = None
        self._last_voltage_time = None
        self._last_heading_time = None

    def connect(self):
        if not MAVLINK_OK:
            print("[vehicle] pymavlink yok. Simülasyon modunda devam.")
            self.sim_mode = True
            return False

        try:
            self.master = mavutil.mavlink_connection(self.connection, baud=self.baudrate)
            self.master.wait_heartbeat(timeout=self.heartbeat_timeout)
            self.sim_mode = False
            print("[vehicle] Pixhawk bağlantısı kuruldu.")
            # SYS_STATUS warm-up: heartbeat geldi ama SYS_STATUS henüz queue'ya
            # düşmediyse startup'taki ilk read_sensors None döner ve aracı
            # açmaz. Kısa süre pollla, cache dolsun.
            self._warm_up_sensors(timeout=2.0)
            return True
        except Exception as e:
            print(f"[vehicle] Bağlantı kurulamadı: {e}")
            self.master = None
            self.sim_mode = True
            return False

    def _warm_up_sensors(self, timeout=2.0):
        """SYS_STATUS gelene kadar (ya da timeout) queue'yu boşalt.
        connect() içinden çağrılır, _drain_messages aynı cache'i doldurur."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline and self._cached_voltage is None:
            self._drain_messages()
            if self._cached_voltage is None:
                time.sleep(0.02)
        if self._cached_voltage is None:
            print("[vehicle] SYS_STATUS warm-up timeout — startup yine de denenecek.")

    def set_mode(self, mode_name="ALT_HOLD"):
        if self.sim_mode:
            print(f"[vehicle] Sim modunda mod ayarı atlandı: {mode_name}")
            return True

        try:
            mode_id = self.master.mode_mapping().get(mode_name)
            if mode_id is None:
                return False

            self.master.set_mode(mode_id)
            return True
        except Exception as e:
            print(f"[vehicle] Mod ayarlanamadı: {e}")
            return False

    def arm(self):
        if self.sim_mode:
            self.armed = True
            print("[vehicle] Sim modunda arm edildi.")
            return True

        try:
            self.master.arducopter_arm()
            self.armed = True
            return True
        except Exception as e:
            print(f"[vehicle] Arm hatası: {e}")
            return False

    def disarm(self):
        if self.sim_mode:
            self.armed = False
            print("[vehicle] Sim modunda disarm edildi.")
            return True

        try:
            self.master.arducopter_disarm()
            self.armed = False
            return True
        except Exception as e:
            print(f"[vehicle] Disarm hatası: {e}")
            return False

    def read_sensors(self):
        if self.sim_mode:
            return {
                "voltage": self._sim_voltage,
                "heading": None,
                "timestamp": time.monotonic(),
            }

        try:
            self._drain_messages()

            # Hiç voltage gelmemişse None döndür - sahte 0V verme
            if self._cached_voltage is None:
                return None

            return {
                "voltage": self._cached_voltage,
                # heading None ise None bırak — 0 (kuzey) ile karıştırılmasın.
                "heading": self._cached_heading,
                # monotonic — sistem saati kaymalarına immün.
                "timestamp": self._last_voltage_time,
            }
        except Exception as e:
            print(f"[vehicle] Sensör okuma hatası: {e}")
            return None

    def _drain_messages(self):
        """MAVLink queue'yu non-blocking olarak boşalt; SYS_STATUS / VFR_HUD
        gelirse cache'leri güncelle. recv_match(type=X, blocking=False) tek
        type ararken type-mismatch mesajları discard ediyor — bu loop hem
        tüm mesaj türlerini tek geçişte yakalar hem buffer'ı boş tutar."""
        if self.master is None:
            return
        now = time.monotonic()
        # Sonsuz dönmesin diye üst sınır; pratikte burst nadir.
        for _ in range(256):
            msg = self.master.recv_match(blocking=False)
            if msg is None:
                break
            mtype = msg.get_type()
            if mtype == "SYS_STATUS":
                self._cached_voltage = msg.voltage_battery / 1000.0
                self._last_voltage_time = now
            elif mtype == "VFR_HUD":
                self._cached_heading = getattr(msg, "heading", None)
                self._last_heading_time = now

    def send_rc(self, yaw=0, forward=0, vertical=0):
        """
        yaw/forward/vertical: PWM offset (-pwm_range..+pwm_range, sifir = neutral).
        vertical: Ultras dikey motorlar (RCMAP_THROTTLE). Pozitif yukari kabul.
        *_reverse aktifse offset negate edilir — config'den ayarlanir.
        """
        yaw_eff = -int(yaw) if self.yaw_reverse else int(yaw)
        forward_eff = -int(forward) if self.forward_reverse else int(forward)
        vertical_eff = -int(vertical) if self.vertical_reverse else int(vertical)

        self.last_rc["yaw"] = yaw_eff
        self.last_rc["forward"] = forward_eff
        self.last_rc["vertical"] = vertical_eff

        if self.sim_mode:
            return True

        try:
            yaw_pwm = self._limit_pwm(self.pwm_base + yaw_eff)
            forward_pwm = self._limit_pwm(self.pwm_base + forward_eff)
            vertical_pwm = self._limit_pwm(self.pwm_base + vertical_eff)

            # 8 kanal slot'u (RC_CHANNELS_OVERRIDE), 65535 = "değiştirme"
            channels = [65535] * 8
            channels[self.yaw_channel - 1] = yaw_pwm
            channels[self.forward_channel - 1] = forward_pwm
            channels[self.vertical_channel - 1] = vertical_pwm

            self.master.mav.rc_channels_override_send(
                self.master.target_system,
                self.master.target_component,
                *channels,
            )
            return True
        except Exception as e:
            print(f"[vehicle] RC gönderme hatası: {e}")
            return False

    def stop(self):
        return self.send_rc(yaw=0, forward=0, vertical=0)

    def disconnect(self):
        self.master = None
        return True

    def _limit_pwm(self, value):
        return max(self.pwm_min, min(self.pwm_max, value))