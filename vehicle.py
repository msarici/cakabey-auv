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
                 pwm_base=1500, pwm_min=1100, pwm_max=1900,
                 allow_sim_fallback=False):
        """
        flight_mode: ArduSub için tipik seçenekler MANUAL / STABILIZE / ALT_HOLD.
        yaw_channel/forward_channel: ArduSub RCMAP_YAW / RCMAP_FORWARD parametreleri ile
            uyumlu olmalı. Mission Planner / QGC'de doğrula. Default: yaw=4, forward=5.
        pwm_base/min/max: motor PWM aralığı (1100-1900 us, neutral 1500).
        allow_sim_fallback: Pixhawk bağlantısı kurulamazsa sim moduna geçmesine izin
            verir. Production'da False (görev güvenliği). Geliştirme'de True.
        """
        yaw_channel = int(yaw_channel)
        forward_channel = int(forward_channel)
        if not (1 <= yaw_channel <= 8):
            raise ValueError(f"yaw_channel 1..8 aralığında olmalı, alındı: {yaw_channel}")
        if not (1 <= forward_channel <= 8):
            raise ValueError(f"forward_channel 1..8 aralığında olmalı, alındı: {forward_channel}")
        if yaw_channel == forward_channel:
            raise ValueError(f"yaw_channel ve forward_channel aynı olamaz: {yaw_channel}")
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
        self.pwm_base = pwm_base
        self.pwm_min = pwm_min
        self.pwm_max = pwm_max
        self.allow_sim_fallback = allow_sim_fallback

        self.master = None
        self.sim_mode = True
        self.armed = False
        self.last_rc = {"yaw": 0, "forward": 0}
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
            return True
        except Exception as e:
            print(f"[vehicle] Bağlantı kurulamadı: {e}")
            self.master = None
            self.sim_mode = True
            return False

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
                "heading": 0,
                "timestamp": time.time(),
            }

        try:
            now = time.time()

            # SYS_STATUS varsa cache'i güncelle
            msg = self.master.recv_match(type="SYS_STATUS", blocking=False)
            if msg is not None:
                self._cached_voltage = msg.voltage_battery / 1000.0
                self._last_voltage_time = now

            # VFR_HUD varsa cache'i güncelle
            att = self.master.recv_match(type="VFR_HUD", blocking=False)
            if att is not None:
                self._cached_heading = getattr(att, "heading", 0)
                self._last_heading_time = now

            # Hiç voltage gelmemişse None döndür - sahte 0V verme
            if self._cached_voltage is None:
                return None

            return {
                "voltage": self._cached_voltage,
                "heading": self._cached_heading if self._cached_heading is not None else 0,
                "timestamp": self._last_voltage_time if self._last_voltage_time else now,
            }
        except Exception as e:
            print(f"[vehicle] Sensör okuma hatası: {e}")
            return None

    def send_rc(self, yaw=0, forward=0):
        self.last_rc["yaw"] = int(yaw)
        self.last_rc["forward"] = int(forward)

        if self.sim_mode:
            return True

        try:
            yaw_pwm = self._limit_pwm(self.pwm_base + int(yaw))
            forward_pwm = self._limit_pwm(self.pwm_base + int(forward))

            # 8 kanal slot'u (RC_CHANNELS_OVERRIDE), 65535 = "değiştirme"
            channels = [65535] * 8
            channels[self.yaw_channel - 1] = yaw_pwm
            channels[self.forward_channel - 1] = forward_pwm

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
        return self.send_rc(yaw=0, forward=0)

    def disconnect(self):
        self.master = None
        return True

    def _limit_pwm(self, value):
        return max(self.pwm_min, min(self.pwm_max, value))