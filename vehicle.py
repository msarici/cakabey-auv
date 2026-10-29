"""
vehicle.py — Araç Arayüzü
Çakabey AUV | TEKNOCAK 2026

Gerçek Pixhawk varsa MAVLink ile konuşur.
Simülasyon yalnızca açıkça seçilirse kullanılır.

read_sensors için cache pattern:
MAVLink mesajları her frame gelmeyebilir (blocking=False).
Son geçerli değer saklanır, yeni mesaj gelene kadar cache'den döner.
Bu sayede tek bir frame kaybı sahte sıfır değer üretmez.
"""

import math
import os
import re
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
                 allow_sim_fallback=False, simulation=False,
                 expected_system=1, expected_component=1, require_signing=False):
        """
        flight_mode: ArduSub için tipik seçenekler MANUAL / STABILIZE / ALT_HOLD.
        yaw_channel/forward_channel/vertical_channel: ArduSub RCMAP_* parametreleri ile
            uyumlu olmalı. Mission Planner / QGC'de doğrula.
            Default ArduSub mapping: yaw=4, forward=5, vertical=3 (RCMAP_THROTTLE).
        *_reverse: kanal yonu ters cikiyorsa True yap — PWM offset'ini negate eder.
            Suya girmeden once mutlaka tek tek dogrula (havada test, her motor sirayla).
        pwm_base/min/max: motor PWM aralığı (1100-1900 us, neutral 1500).
        simulation: True ise Pixhawk bağlantısı denenmez (donanımsız --sim).
        expected_system/component: pinned MAVLink source IDs; None explicitly
            opts into discovery for that ID. Defaults match ArduSub 1/1.
        require_signing: require CAKABEY_MAVLINK_KEY even on local serial ports.
            Non-serial transports always require signing. The environment key
            must be 32 bytes encoded as 64 hex characters; never stored in YAML.
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

        if not math.isfinite(float(heartbeat_timeout)) or float(heartbeat_timeout) <= 0:
            raise ValueError("heartbeat_timeout must be positive and finite")

        for name, value in (("expected_system", expected_system),
                            ("expected_component", expected_component)):
            if value is not None and (type(value) is not int or not 1 <= value <= 255):
                raise ValueError(f"{name} must be an integer from 1 to 255 or None")
        if type(require_signing) is not bool:
            raise ValueError("require_signing must be boolean")
        if not isinstance(connection, str) or not connection:
            raise ValueError("connection must be a non-empty string")
        self.expected_system = expected_system
        self.expected_component = expected_component
        self.require_signing = require_signing
        self._signing_enabled = False
        self.connection = connection
        self.baudrate = baudrate
        self.heartbeat_timeout = float(heartbeat_timeout)
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

        self.simulation = bool(simulation)
        self.master = None
        self.sim_mode = self.simulation or bool(allow_sim_fallback)
        self.armed = False
        self.last_rc = {"yaw": 0, "forward": 0, "vertical": 0}
        self._sim_voltage = 16.0

        # Sensör cache - en son geçerli değerler
        self._cached_voltage = None
        self._cached_heading = None
        self._last_voltage_time = None
        self._last_heading_time = None
        self._target = None
        self._last_heartbeat_time = None
        self._heartbeat_sequence = 0
        self._custom_mode = None

    def connect(self):
        if self.simulation:
            self.sim_mode = True
            return True

        if not MAVLINK_OK:
            print("[vehicle] pymavlink yok. Bağlantı kurulamadı.")
            self.sim_mode = bool(self.allow_sim_fallback)
            return False

        # A reconnect must not reuse old telemetry or arming observations.
        self.disconnect()
        self._cached_voltage = self._cached_heading = None
        self._last_voltage_time = self._last_heading_time = None
        self._target = None
        self._signing_enabled = False
        self._last_heartbeat_time = None
        self._heartbeat_sequence = 0
        self._custom_mode = None
        self.armed = False
        try:
            key = self._load_signing_key()
            if key is not None:
                # setup_signing needs a MAVLink2 parser before the first packet;
                # automatic v1->v2 switching would replace parser/signing state.
                os.environ["MAVLINK20"] = "1"
                mavutil.set_dialect("ardupilotmega")
            self.master = mavutil.mavlink_connection(self.connection, baud=self.baudrate)
            if key is not None:
                self._configure_signing(key)
            heartbeat = self.master.wait_heartbeat(timeout=self.heartbeat_timeout)
            if heartbeat is None:
                raise TimeoutError("Pixhawk heartbeat alınamadı")
            if (heartbeat.autopilot == mavutil.mavlink.MAV_AUTOPILOT_INVALID
                    or heartbeat.type == mavutil.mavlink.MAV_TYPE_GCS):
                raise ValueError("Heartbeat does not identify an autopilot")
            source = (heartbeat.get_srcSystem(), heartbeat.get_srcComponent())
            if ((self.expected_system is not None and source[0] != self.expected_system)
                    or (self.expected_component is not None and source[1] != self.expected_component)):
                raise ValueError("Heartbeat source does not match the configured autopilot")
            if self._signing_enabled and not heartbeat.get_signed():
                raise ValueError("Unsigned autopilot heartbeat rejected")
            self._target = source
            self.master.target_system, self.master.target_component = self._target
            self._handle_message(heartbeat)
            self.sim_mode = False
            print("[vehicle] Pixhawk bağlantısı kuruldu.")
            # SYS_STATUS warm-up: heartbeat geldi ama SYS_STATUS henüz queue'ya
            # düşmediyse startup'taki ilk read_sensors None döner ve aracı
            # açmaz. Kısa süre pollla, cache dolsun.
            self._warm_up_sensors(timeout=2.0)
            return True
        except Exception as e:
            print(f"[vehicle] Bağlantı kurulamadı: {e}")
            self.disconnect()
            self.sim_mode = bool(self.allow_sim_fallback)
            return False

    def _load_signing_key(self):
        raw = os.environ.get("CAKABEY_MAVLINK_KEY", "")
        if raw:
            if len(raw) != 64 or re.fullmatch(r"[0-9a-fA-F]{64}", raw) is None:
                raise ValueError("CAKABEY_MAVLINK_KEY must contain exactly 64 hex characters")
            return bytes.fromhex(raw)
        # An unsigned local serial link is a deliberate physical-trust policy.
        # All other transports, including UDP/TCP/Unix/log paths, fail closed.
        local_serial = (re.fullmatch(r"/dev/(?:tty[^/]+|serial/by-(?:id|path)/[^/]+)", self.connection)
                        or re.fullmatch(r"COM[1-9][0-9]*", self.connection, re.IGNORECASE))
        if self.require_signing or not local_serial:
            raise ValueError("MAVLink signing key required for this connection")
        return None

    def _configure_signing(self, key):
        self.master.setup_signing(key, sign_outgoing=True, allow_unsigned_callback=None)
        signing = self.master.mav.signing
        original_check = self.master.mav.check_signature

        def checked_signature(*args):
            # pymavlink 2.4.50 updates stream_timestamps before checking the MAC.
            # Restore those counters on failure, so forged future timestamps
            # cannot prevent a later authentic message from being received.
            previous_streams = dict(signing.stream_timestamps)
            previous_timestamp = signing.timestamp
            try:
                accepted = original_check(*args)
            except Exception:
                signing.stream_timestamps = previous_streams
                signing.timestamp = previous_timestamp
                raise
            if not accepted:
                signing.stream_timestamps = previous_streams
                signing.timestamp = previous_timestamp
            return accepted

        self.master.mav.check_signature = checked_signature
        self._signing_enabled = True

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
            return self._wait_for_heartbeat_state(lambda: self._custom_mode == mode_id)
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
            return self._wait_for_heartbeat_state(lambda: self.armed)
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
            return self._wait_for_heartbeat_state(lambda: not self.armed)
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
                **({"heartbeat_timestamp": self._last_heartbeat_time}
                   if self._target is not None else {}),
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
        # Bound processing so a noisy MAVLink link cannot monopolize the loop.
        for _ in range(256):
            msg = self.master.recv_match(blocking=False)
            if msg is None:
                break
            self._handle_message(msg)

    def _handle_message(self, msg):
        # Source IDs are routing checks, not cryptographic authentication.
        if self._target is None or (msg.get_srcSystem(), msg.get_srcComponent()) != self._target:
            return
        if self._signing_enabled and not msg.get_signed():
            return
        now = time.monotonic()
        mtype = msg.get_type()
        if mtype == "SYS_STATUS":
            voltage_mv = msg.voltage_battery
            # MAVLink UINT16_MAX means unknown; it must not look like 65.535 V.
            if not isinstance(voltage_mv, (int, float)) or not math.isfinite(voltage_mv) or not 0 < voltage_mv < 65535:
                self._cached_voltage = None
                self._last_voltage_time = None
                return
            self._cached_voltage = voltage_mv / 1000.0
            self._last_voltage_time = now
        elif mtype == "VFR_HUD":
            self._cached_heading = getattr(msg, "heading", None)
            self._last_heading_time = now
        elif mtype == "HEARTBEAT":
            self._last_heartbeat_time = now
            self._heartbeat_sequence += 1
            self.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            self._custom_mode = msg.custom_mode

    def _wait_for_heartbeat_state(self, predicate):
        """Confirm the observed state with a new heartbeat, within a fixed deadline.

        A successful socket write or COMMAND_ACK alone does not prove that the
        autopilot entered the requested mode/armed state.
        """
        sequence = self._heartbeat_sequence
        deadline = time.monotonic() + self.heartbeat_timeout
        while time.monotonic() < deadline:
            self._drain_messages()
            if self._heartbeat_sequence > sequence and predicate():
                return True
            time.sleep(0.01)
        return False

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
        master, self.master = self.master, None
        if master is not None:
            try:
                master.close()
            except Exception as e:
                print(f"[vehicle] Bağlantı kapatma hatası: {e}")
                return False
        return True

    def _limit_pwm(self, value):
        return max(self.pwm_min, min(self.pwm_max, value))