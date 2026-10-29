"""
main.py — Ana Kontrol Döngüsü
Çakabey AUV | TEKNOCAK 2026
Yazar: Mert Sarıcı

Ana akış:
güvenlik -> kamera -> tespit -> FSM -> motor komutu -> overlay/log -> kapanış
"""

import sys
import time
import argparse
import logging
import math
import cv2

try:
    import yaml
    YAML_OK = True
except ImportError:
    YAML_OK = False

from camera import Camera
from pipe_detector import PipeDetector
from pid_controller import PIDController
from fsm import FSM
from vehicle import Vehicle
from safety import SafetyMonitor
from distance import DistanceEstimator
from debug_overlay import draw_overlay
from telemetry_logger import TelemetryLogger
from ground_station import GroundStation
from anomaly_detector import AnomalyDetector
from video_sender import VideoSender
from command_link import CommandReceiver


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
log = logging.getLogger("cakabey")


def load_config(path="config.yaml"):
    """Read configuration; an unreadable deployment config must stop startup."""
    if not YAML_OK:
        raise RuntimeError("PyYAML gerekli; yapılandırma doğrulanamadı")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError("Config bir YAML mapping olmalı")
    return cfg


def cfg_get(cfg, *keys, default=None):
    """İç içe config değerini güvenli şekilde al."""
    value = cfg
    if value is None:
        return default

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def startup(vehicle, safety=None):
    """
    Araç başlatma sırası.
    Pixhawk bağlantısı yoksa: vehicle.allow_sim_fallback True ise sim modda
    devam eder; False ise startup başarısız olur ve main güvenli çıkış yapar.
    """
    log.info("=" * 45)
    log.info("CAKABEY AUV - BASLATMA")
    log.info("=" * 45)

    if safety is not None:
        status = safety.check(None)
        if status["emergency"]:
            log.critical(status["reason"])
            return False

    connected = vehicle.connect()

    if not connected:
        if vehicle.allow_sim_fallback:
            log.warning("Pixhawk bulunamadi. SIM FALLBACK ENABLED - simulasyon modunda devam ediliyor.")
            return True
        log.error("Pixhawk bulunamadi ve sim fallback kapali. Baslatma iptal.")
        return False

    sensor = vehicle.read_sensors()
    if sensor is None:
        log.error("Başlatmada sensör verisi alınamadı.")
        return False

    if safety is not None:
        status = safety.check(sensor)
        if status["emergency"]:
            log.critical(status["reason"])
            return False

    voltage = sensor.get("voltage", 0.0)
    heading = sensor.get("heading")

    if safety is None and (not isinstance(voltage, (int, float)) or not math.isfinite(voltage) or voltage <= 12.0):
        log.error("Batarya kritik veya geçersiz: %r", voltage)
        return False

    heading_str = "—" if heading is None else f"{heading}°"
    log.info(f"Batarya: {voltage:.1f}V | Heading: {heading_str}")

    mode = vehicle.flight_mode
    if not vehicle.set_mode(mode):
        log.error(f"{mode} modu ayarlanamadı.")
        return False

    if safety is not None:
        latest = vehicle.read_sensors()
        if latest is None:
            log.error("Arm öncesinde sensör verisi kayboldu")
            return False
        status = safety.check(latest)
        if status["emergency"]:
            log.critical(status["reason"])
            return False

    if not vehicle.arm():
        log.error("Arm başarısız.")
        return False

    log.info("Başlatma tamam. Ana döngü başlıyor.")
    return True


def default_detection(frame):
    """Tespit patlarsa sistemi düşürmemek için boş sonuç döndür."""
    h, w = frame.shape[:2]
    return {
        "found": False,
        "cx": 0,
        "cy": 0,
        "bbox": (0, 0, 0, 0),
        "area": 0,
        "error_x": 0,
        "error_y": 0,
        "width": 0,
        "height": 0,
        "frame_center": (w // 2, h // 2),
        "mask": None,
    }


def validate_config(cfg, simulation=False):
    if not isinstance(cfg, dict):
        raise ValueError("Config bir mapping olmalı")
    def finite_values(value):
        if isinstance(value, dict):
            for item in value.values():
                finite_values(item)
        elif isinstance(value, list):
            for item in value:
                finite_values(item)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Config NaN veya sonsuz değer içeremez")
    finite_values(cfg)
    for section in ("camera", "vehicle", "safety", "command", "pid", "fsm"):
        if section in cfg and not isinstance(cfg[section], dict):
            raise ValueError(f"{section} bir mapping olmalı")
    for section, key, default in (
        ("safety", "watchdog_timeout", 2.0),
        ("command", "stale_after_s", 0.5),
        ("vehicle", "heartbeat_timeout", 3.0),
    ):
        value = cfg_get(cfg, section, key, default=default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{section}.{key} sonlu ve pozitif olmalı")
    for section, key, default in (("camera", "max_frame_loss", 30), ("safety", "max_sensor_loss", 10)):
        value = cfg_get(cfg, section, key, default=default)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{section}.{key} pozitif tam sayı olmalı")
    if not simulation and cfg_get(cfg, "safety", "leak_pin", default=17) is None:
        raise ValueError("Gerçek kullanımda sızıntı sensörü yapılandırılmalı")
    for section, key, default in (("command", "enabled", True), ("safety", "leak_active_high", True)):
        if type(cfg_get(cfg, section, key, default=default)) is not bool:
            raise ValueError(f"{section}.{key} boolean olmalı")


def main():
    parser = argparse.ArgumentParser(description="Çakabey AUV Ana Kontrol")
    parser.add_argument("--source", default=None, choices=["csi", "webcam", "test"],
                        help="Kamera kaynağı. Verilmezse config'den okunur.")
    parser.add_argument("--config", default="config.yaml",
                        help="Config dosyası")
    parser.add_argument("--no-display", action="store_true",
                        help="Görüntü penceresini kapatır")
    parser.add_argument("--sim", action="store_true",
                        help="Donanımsız simülasyon: Pixhawk bağlantısı ve GPIO kullanılmaz; "
                             "kamera test fallback açık. Production'da kullanma.")
    args = parser.parse_args()

    # config
    cfg = load_config(args.config)

    resources = {}
    try:
        _run(args, cfg, resources)
    finally:
        # Motor stop/disarm attempts must run even after partial startup, and
        # one failing cleanup must never prevent the remaining operations.
        for name, methods in (
            ("vehicle", ("stop", "disarm", "disconnect")),
            ("safety", ("cleanup",)), ("camera", ("close",)),
            ("telemetry", ("close",)), ("ground", ("close",)),
            ("video_sender", ("close",)), ("command_rx", ("close",)),
        ):
            obj = resources.get(name)
            if obj is not None:
                for method in methods:
                    try:
                        if getattr(obj, method)() is False:
                            log.error("%s.%s başarısız", name, method)
                    except Exception as e:
                        log.error("%s.%s kapanış hatası: %s", name, method, e)
        cv2.destroyAllWindows()


def _run(args, cfg, resources):
    validate_config(cfg, args.sim)
    # source önce argümandan gelsin, yoksa config'den gelsin
    selected_source = args.source
    if selected_source is None:
        selected_source = cfg_get(cfg, "camera", "source", default="csi")

    if not args.sim and selected_source == "test":
        raise ValueError("Test kamerası için --sim gerekli")

    # --sim: açıkça seçilen donanımsız test modu
    if args.sim:
        log.warning("=" * 45)
        log.warning("SIM MODE ENABLED — donanim olmadan calisiyor")
        log.warning("Production icin --sim KULLANMA. Bu mod test/gelistirme icin.")
        log.warning("=" * 45)
        sim_camera_fallback = True
    else:
        sim_camera_fallback = False

    # modüller
    camera = Camera(
        source=selected_source,
        width=cfg_get(cfg, "camera", "width", default=640),
        height=cfg_get(cfg, "camera", "height", default=480),
        fps=cfg_get(cfg, "camera", "fps", default=30),
        device_id=cfg_get(cfg, "camera", "device_id", default=0),
        allow_test_fallback=sim_camera_fallback,
    )

    resources["camera"] = camera

    detector = PipeDetector(
        h_min=cfg_get(cfg, "detector", "h_min", default=10),
        h_max=cfg_get(cfg, "detector", "h_max", default=25),
        s_min=cfg_get(cfg, "detector", "s_min", default=100),
        s_max=cfg_get(cfg, "detector", "s_max", default=255),
        v_min=cfg_get(cfg, "detector", "v_min", default=80),
        v_max=cfg_get(cfg, "detector", "v_max", default=255),
        min_area=cfg_get(cfg, "detector", "min_area", default=500),
        blur_kernel=cfg_get(cfg, "detector", "blur_kernel", default=5),
        morph_kernel=cfg_get(cfg, "detector", "morph_kernel", default=5),
    )

    yaw_pid = PIDController(
        kp=cfg_get(cfg, "pid", "yaw", "kp", default=1.0),
        ki=cfg_get(cfg, "pid", "yaw", "ki", default=0.0),
        kd=cfg_get(cfg, "pid", "yaw", "kd", default=0.0),
        output_min=cfg_get(cfg, "pid", "yaw", "output_min", default=-400),
        output_max=cfg_get(cfg, "pid", "yaw", "output_max", default=400),
        integral_limit=cfg_get(cfg, "pid", "yaw", "integral_limit", default=200),
    )

    fsm = FSM(
        lost_timeout=cfg_get(cfg, "fsm", "lost_timeout_frames", default=30),
        found_threshold=cfg_get(cfg, "fsm", "found_threshold_frames", default=3),
        approach_area_min=cfg_get(cfg, "fsm", "approach_area_min", default=2000),
        search_yaw_speed=cfg_get(cfg, "fsm", "search_yaw_speed", default=150),
        forward_base_speed=cfg_get(cfg, "fsm", "forward_base_speed", default=200),
        track_slow_area_multiplier=cfg_get(cfg, "fsm", "track_slow_area_multiplier", default=1.8),
        track_slow_factor=cfg_get(cfg, "fsm", "track_slow_factor", default=0.6),
    )

    vehicle = Vehicle(
        connection=cfg_get(cfg, "vehicle", "connection", default="/dev/ttyACM0"),
        baudrate=cfg_get(cfg, "vehicle", "baudrate", default=115200),
        heartbeat_timeout=cfg_get(cfg, "vehicle", "heartbeat_timeout", default=3.0),
        flight_mode=cfg_get(cfg, "vehicle", "flight_mode", default="MANUAL"),
        yaw_channel=cfg_get(cfg, "vehicle", "yaw_channel", default=4),
        forward_channel=cfg_get(cfg, "vehicle", "forward_channel", default=5),
        vertical_channel=cfg_get(cfg, "vehicle", "vertical_channel", default=3),
        pwm_base=cfg_get(cfg, "vehicle", "pwm_base", default=1500),
        pwm_min=cfg_get(cfg, "vehicle", "pwm_min", default=1100),
        pwm_max=cfg_get(cfg, "vehicle", "pwm_max", default=1900),
        yaw_reverse=cfg_get(cfg, "vehicle", "yaw_reverse", default=False),
        forward_reverse=cfg_get(cfg, "vehicle", "forward_reverse", default=False),
        vertical_reverse=cfg_get(cfg, "vehicle", "vertical_reverse", default=False),
        allow_sim_fallback=False,  # Eski YAML True olsa bile gerçek mod fail-closed.
        simulation=args.sim,
    )

    resources["vehicle"] = vehicle

    safety = SafetyMonitor(
        vehicle,
        warn_voltage=cfg_get(cfg, "safety", "battery_warn_voltage", default=13.0),
        critical_voltage=cfg_get(cfg, "safety", "battery_critical_voltage", default=12.0),
        watchdog_timeout=cfg_get(cfg, "safety", "watchdog_timeout", default=2.0),
        leak_pin=None if args.sim else cfg_get(cfg, "safety", "leak_pin", default=17),
        leak_active_high=cfg_get(cfg, "safety", "leak_active_high", default=True),
    )

    resources["safety"] = safety

    distance_estimator = DistanceEstimator(
        method=cfg_get(cfg, "distance", "method", default="pinhole"),
        pipe_real_width_cm=cfg_get(cfg, "distance", "pipe_real_width_cm", default=20.0),
        focal_length_px=cfg_get(cfg, "distance", "focal_length_px", default=500.0),
        laser_baseline_cm=cfg_get(cfg, "distance", "laser_baseline_cm", default=15.0),
    )

    telemetry = TelemetryLogger(
        directory=cfg_get(cfg, "log", "directory", default="logs"),
        enabled=cfg_get(cfg, "log", "csv_enabled", default=True),
        flush_interval=cfg_get(cfg, "log", "flush_interval", default=30),
    )

    resources["telemetry"] = telemetry

    ground = GroundStation(
        host=cfg_get(cfg, "ground_station", "host", default="192.168.2.1"),
        port=cfg_get(cfg, "ground_station", "port", default=14651),
        enabled=cfg_get(cfg, "ground_station", "enabled", default=True),
        send_interval_s=cfg_get(cfg, "ground_station", "send_interval_s", default=0.1),
    )

    resources["ground"] = ground

    video_sender = VideoSender(
        host=cfg_get(cfg, "video", "host", default="192.168.2.1"),
        port=cfg_get(cfg, "video", "port", default=14652),
        enabled=cfg_get(cfg, "video", "enabled", default=True),
        send_interval_s=cfg_get(cfg, "video", "send_interval_s", default=0.066),
        jpeg_quality=cfg_get(cfg, "video", "jpeg_quality", default=60),
        max_width=cfg_get(cfg, "video", "max_width", default=640),
    )

    resources["video_sender"] = video_sender

    command_rx = CommandReceiver(
        bind="127.0.0.1" if args.sim else cfg_get(cfg, "command", "bind", default="0.0.0.0"),
        port=cfg_get(cfg, "command", "port", default=14653),
        stale_after_s=cfg_get(cfg, "command", "stale_after_s", default=0.5),
        allow_insecure=args.sim,
        enabled=cfg_get(cfg, "command", "enabled", default=True),
    )

    resources["command_rx"] = command_rx

    # PWM offset scale: vehicle.send_rc'ye verilen sayilar (-pwm_range..+pwm_range).
    # Manuel komut -1..1'den bu araliga cevriliyor.
    manual_yaw_scale = cfg_get(cfg, "command", "manual_yaw_scale", default=400)
    manual_fwd_scale = cfg_get(cfg, "command", "manual_fwd_scale", default=400)
    manual_vrt_scale = cfg_get(cfg, "command", "manual_vertical_scale", default=400)
    # Manuel modda ani komut yerine bu kadar PWM/saniye'ye limitle (ESC nazik).
    # 0 = limit yok. Tipik 2000 (saniyede tam ranj).
    slew_rate_pwm_per_s = cfg_get(cfg, "command", "slew_rate_pwm_per_s", default=2000)

    anomaly_enabled = cfg_get(cfg, "anomaly", "enabled", default=True)
    anomaly_detector = AnomalyDetector(
        algae_ratio_thresh=cfg_get(cfg, "anomaly", "algae_ratio_thresh", default=0.05),
        rust_ratio_thresh=cfg_get(cfg, "anomaly", "rust_ratio_thresh", default=0.03),
        crack_min_lines=cfg_get(cfg, "anomaly", "crack_min_lines", default=1),
        break_min_contour_area=cfg_get(cfg, "anomaly", "break_min_contour_area", default=200),
        missing_aspect_min=cfg_get(cfg, "anomaly", "missing_aspect_min", default=3.0),
    )

    # başlangıç ayarları
    max_frame_loss = cfg_get(cfg, "camera", "max_frame_loss", default=30)
    max_sensor_loss = cfg_get(cfg, "safety", "max_sensor_loss", default=10)
    overlay_enabled = cfg_get(cfg, "log", "overlay_enabled", default=True)

    fps = 0.0
    fps_counter = 0
    fps_start = time.time()

    frame_loss_count = 0
    sensor_loss_count = 0

    # kamera aç
    try:
        ok = camera.open()
        if not ok:
            log.error("Kamera açılamadı ve test fallback kapalı. Sistem güvenli şekilde durduruluyor.")
            sys.exit(1)
    except Exception as e:
        log.error(f"Kamera başlatılamadı: {e}")
        sys.exit(1)

    telemetry.start()

    if not startup(vehicle, safety):
        log.error("Sistem başlatılamadı. Çıkılıyor.")
        sys.exit(1)

    # Mod takibi: command receiver istek getirir, FSM'i ona gore set ederiz.
    current_mode = "auto"

    # Slew rate icin onceki PWM cikislari (ESC inrush koruma).
    prev_yaw_cmd = 0
    prev_fwd_cmd = 0
    prev_vrt_cmd = 0
    last_motor_t = time.monotonic()

    def _slew(target, prev, dt, rate):
        if rate <= 0 or dt <= 0:
            return int(target)
        max_step = rate * dt
        diff = target - prev
        if diff > max_step:
            return int(prev + max_step)
        if diff < -max_step:
            return int(prev - max_step)
        return int(target)

    try:
        while True:
            # ---------------- KOMUT KANALI ----------------
            # Once oku ki frame karari komutla tutarli olsun.
            command_rx.poll()
            cmd, stale = command_rx.get_command()
            requested_mode = cmd.get("mode", "auto")

            # Manual link loss cannot silently re-enable autonomous thrust.
            # An accepted E-stop terminates this run and is independent of camera.
            emergency_cmd = bool(cmd.get("emergency_stop", False))
            if emergency_cmd or (stale and current_mode == "manual"):
                log.critical("Acil dur / manuel komut bağlantısı kaybı")
                vehicle.stop()
                break

            if requested_mode != current_mode:
                current_mode = requested_mode
                if current_mode == "manual":
                    fsm.set_manual()
                else:
                    fsm.set_auto()
                yaw_pid.reset()

            # ---------------- GÜVENLİK ----------------
            sensor = vehicle.read_sensors()

            if sensor is None:
                sensor_loss_count += 1
                log.warning(f"Sensör verisi alınamadı ({sensor_loss_count}/{max_sensor_loss})")
                if sensor_loss_count >= max_sensor_loss:
                    log.critical("Sensör verisi uzun süredir yok. Sistem güvenlik nedeniyle durduruluyor.")
                    vehicle.stop()
                    break
            else:
                sensor_loss_count = 0

            # Safety check sensor None olsa bile çağrılır — sızıntı GPIO
            # Pixhawk'tan bağımsız; pil/watchdog kontrolu sensor olmadan zaten skip ediliyor.
            safety_status = safety.check(sensor)

            if safety_status.get("emergency", False):
                log.critical(safety_status.get("reason", "Acil durum"))
                vehicle.stop()
                break

            for warning in safety_status.get("warnings", []):
                log.warning(warning)

            if sensor is None:
                vehicle.stop()
                prev_yaw_cmd = prev_fwd_cmd = prev_vrt_cmd = 0
                time.sleep(0.01)
                continue

            # ---------------- FRAME ----------------
            frame = camera.read()

            if frame is None:
                vehicle.stop()
                prev_yaw_cmd = prev_fwd_cmd = prev_vrt_cmd = 0
                frame_loss_count += 1
                log.warning(f"Frame alınamadı ({frame_loss_count}/{max_frame_loss})")

                if frame_loss_count >= max_frame_loss:
                    log.error("Art arda çok fazla frame kaybı oldu. Sistem durduruluyor.")
                    break

                time.sleep(0.01)
                continue

            frame_loss_count = 0

            # ---------------- BORU TESPİT ----------------
            try:
                detection = detector.detect(frame)
            except Exception as e:
                log.error(f"Tespit hatası: {e}")
                vehicle.stop()
                break

            # ---------------- ANOMALY ----------------
            anomalies = []
            if anomaly_enabled:
                try:
                    anomalies = anomaly_detector.detect(frame, detection)
                except Exception as e:
                    log.error(f"Anomaly tespit hatası: {e}")
                    anomalies = []

            # ---------------- FSM ----------------
            try:
                action = fsm.update(detection)
            except Exception as e:
                log.error(f"FSM hatası: {e}")
                vehicle.stop()
                break

            # ---------------- KOMUT HESABI ----------------
            yaw_cmd = 0
            fwd_cmd = 0
            vrt_cmd = 0
            state = action.get("state", "LOST")

            if emergency_cmd:
                # Acil dur: mod ne olursa olsun motorlar sifir.
                yaw_cmd = 0
                fwd_cmd = 0
                vrt_cmd = 0
                yaw_pid.reset()

            elif state == FSM.MANUAL:
                # Yer istasyonu surusunde: -1..1 -> PWM offset.
                yaw_cmd = int(round(cmd.get("yaw", 0.0) * manual_yaw_scale))
                fwd_cmd = int(round(cmd.get("fwd", 0.0) * manual_fwd_scale))
                vrt_cmd = int(round(cmd.get("vertical", 0.0) * manual_vrt_scale))

            elif state in (FSM.SEARCH, FSM.LOST):
                yaw_cmd = action.get("search_yaw", 150)
                fwd_cmd = 0
                yaw_pid.reset()

            elif state == FSM.APPROACH:
                if detection.get("found", False):
                    yaw_cmd = int(yaw_pid.compute(detection.get("error_x", 0)))
                    fwd_cmd = action.get("forward_speed", 0)
                else:
                    yaw_cmd = 0
                    fwd_cmd = 0
                    yaw_pid.reset()

            elif state == FSM.TRACK:
                if detection.get("found", False):
                    yaw_cmd = int(yaw_pid.compute(detection.get("error_x", 0)))
                    fwd_cmd = action.get("forward_speed", 0)
                else:
                    yaw_cmd = 0
                    fwd_cmd = 0
                    yaw_pid.reset()

            else:
                yaw_cmd = 0
                fwd_cmd = 0
                yaw_pid.reset()

            # ---------------- SLEW RATE (ESC korumasi) ----------------
            # Acil durda slew uygulama: en hizli sifirla.
            now_motor = time.monotonic()
            dt_motor = max(0.0, now_motor - last_motor_t)
            last_motor_t = now_motor
            if emergency_cmd or slew_rate_pwm_per_s <= 0:
                prev_yaw_cmd = yaw_cmd
                prev_fwd_cmd = fwd_cmd
                prev_vrt_cmd = vrt_cmd
            else:
                yaw_cmd = _slew(yaw_cmd, prev_yaw_cmd, dt_motor, slew_rate_pwm_per_s)
                fwd_cmd = _slew(fwd_cmd, prev_fwd_cmd, dt_motor, slew_rate_pwm_per_s)
                vrt_cmd = _slew(vrt_cmd, prev_vrt_cmd, dt_motor, slew_rate_pwm_per_s)
                prev_yaw_cmd = yaw_cmd
                prev_fwd_cmd = fwd_cmd
                prev_vrt_cmd = vrt_cmd

            # Processing may have taken longer than the watchdog budget. Recheck
            # the sampled data and GPIO before any motor output, and honor E-stop
            # packets that arrived while processing the frame.
            command_rx.poll()
            latest_cmd, latest_stale = command_rx.get_command()
            if (latest_cmd.get("emergency_stop", False)
                    or (latest_stale and current_mode == "manual")
                    or safety.check(sensor)["emergency"]):
                log.critical("Motor çıkışı öncesi güvenlik kontrolü başarısız")
                vehicle.stop()
                break

            # ---------------- KOMUT GÖNDER ----------------
            rc_ok = vehicle.send_rc(yaw=yaw_cmd, forward=fwd_cmd, vertical=vrt_cmd)
            if not rc_ok:
                log.error("RC komutu gönderilemedi. Sistem durduruluyor.")
                break

            # ---------------- MESAFE ----------------
            # Yöntem config.yaml içinde distance.method ile seçilir.
            # Pinhole için bbox_width yeterli.
            # Lazer için laser_pixel_gap parametresi de gönderilmeli (lazerler monte edildiğinde).
            distance_cm = None
            if detection.get("found", False):
                bbox_width = detection.get("width", 0)
                if bbox_width > 0:
                    distance_cm = distance_estimator.estimate(bbox_width=bbox_width)

            # ---------------- FPS ----------------
            fps_counter += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                fps = fps_counter / elapsed
                fps_counter = 0
                fps_start = time.time()

            # ---------------- LOG ----------------
            telemetry.log(
                action=action,
                detection=detection,
                sensor=sensor,
                yaw_cmd=yaw_cmd,
                fwd_cmd=fwd_cmd,
                fps=fps,
                distance_cm=distance_cm,
                anomalies=anomalies,
            )

            # ---------------- VIDEO STREAM (CAT6 / UDP) ----------------
            # Overlay'li frame'i gondermek yerine ham frame gonderiyoruz:
            # yer istasyonu kendi overlay'ini cizebilir (telemetri ile),
            # ham gorus debug icin daha kullanisli. Overlay'i istersen view'i
            # gondermek icin asagidaki video_sender.send(view) yapmak yeter.
            video_sender.send(frame)

            # ---------------- GROUND TELEMETRY (CAT6 / UDP) ----------------
            # mask gibi NumPy verisi JSON'lanmaz; ham scalar/listeleri gonder.
            ground.send({
                "state": action.get("state", "LOST"),
                "mode": current_mode,
                "command_link": {
                    "stale": bool(cmd.get("stale", False)),
                    "age": cmd.get("age"),
                    "last_seq": cmd.get("seq", -1),
                },
                "detection": {
                    "found": bool(detection.get("found", False)),
                    "cx": int(detection.get("cx", 0)),
                    "cy": int(detection.get("cy", 0)),
                    "area": int(detection.get("area", 0)),
                    "error_x": int(detection.get("error_x", 0)),
                    "error_y": int(detection.get("error_y", 0)),
                    "width": int(detection.get("width", 0)),
                    "height": int(detection.get("height", 0)),
                },
                "sensor": {
                    "voltage": (float(sensor["voltage"])
                                if sensor and sensor.get("voltage") is not None
                                else None),
                    "heading": (int(sensor["heading"])
                                if sensor and sensor.get("heading") is not None
                                else None),
                },
                "control": {
                    "yaw_cmd": int(yaw_cmd),
                    "fwd_cmd": int(fwd_cmd),
                    "vrt_cmd": int(vrt_cmd),
                },
                "fps": float(fps),
                "distance_cm": None if distance_cm is None else float(distance_cm),
                "anomalies": [
                    {
                        "type": str(a["type"]),
                        "bbox": [int(v) for v in a["bbox"]],
                        "confidence": round(float(a["confidence"]), 3),
                        "area_ratio": round(float(a["area_ratio"]), 3),
                    }
                    for a in anomalies
                ],
            })

            # ---------------- GÖRÜNTÜ ----------------
            if not args.no_display and overlay_enabled:
                try:
                    view = draw_overlay(
                        frame,
                        detection,
                        action,
                        sensor=sensor,
                        fps=fps,
                        distance_cm=distance_cm,
                        yaw_cmd=yaw_cmd,
                        fwd_cmd=fwd_cmd,
                        anomalies=anomalies,
                    )
                except Exception as e:
                    log.error(f"Overlay çizim hatası: {e}")
                    view = frame

                cv2.imshow("Cakabey AUV", view)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    log.info("Kullanıcı çıkışı yapıldı.")
                    break
                elif key == ord("r"):
                    fsm.reset()
                    yaw_pid.reset()
                    log.info("FSM ve PID sıfırlandı.")

    except KeyboardInterrupt:
        log.info("Ctrl+C algılandı. Sistem kapatılıyor...")



if __name__ == "__main__":
    main()