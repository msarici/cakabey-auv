"""
main.py — Ana Kontrol Döngüsü
Çakabey AUV | TEKNOCAK 2026
Yazar: Mert Sarıcı

Ana akış:
kamera -> güvenlik -> tespit -> FSM -> motor komutu -> overlay/log -> kapanış
"""

import sys
import time
import argparse
import logging
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
    """Config dosyasını oku. Yoksa varsayılanlarla devam et."""
    if not YAML_OK:
        log.warning("PyYAML kurulu değil. Varsayılan ayarlar kullanılacak.")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        log.warning(f"{path} bulunamadı. Varsayılan ayarlar kullanılacak.")
        return None
    except Exception as e:
        log.error(f"Config okunurken hata oluştu: {e}")
        return None


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


def startup(vehicle):
    """
    Araç başlatma sırası.
    Pixhawk bağlantısı yoksa: vehicle.allow_sim_fallback True ise sim modda
    devam eder; False ise startup başarısız olur ve main güvenli çıkış yapar.
    """
    log.info("=" * 45)
    log.info("CAKABEY AUV - BASLATMA")
    log.info("=" * 45)

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

    voltage = sensor.get("voltage", 0.0)
    heading = sensor.get("heading", 0)

    if voltage > 0 and voltage < 12.0:
        log.error(f"Batarya kritik seviyede: {voltage:.1f}V")
        return False

    log.info(f"Batarya: {voltage:.1f}V | Heading: {heading}°")

    mode = vehicle.flight_mode
    if not vehicle.set_mode(mode):
        log.error(f"{mode} modu ayarlanamadı.")
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


def main():
    parser = argparse.ArgumentParser(description="Çakabey AUV Ana Kontrol")
    parser.add_argument("--source", default=None, choices=["csi", "webcam", "test"],
                        help="Kamera kaynağı. Verilmezse config'den okunur.")
    parser.add_argument("--config", default="config.yaml",
                        help="Config dosyası")
    parser.add_argument("--no-display", action="store_true",
                        help="Görüntü penceresini kapatır")
    parser.add_argument("--sim", action="store_true",
                        help="Donanımsız simülasyon modu: kamera ve Pixhawk yoksa "
                             "test moduna düşmeye izin verir. Production'da kullanma.")
    args = parser.parse_args()

    # config
    cfg = load_config(args.config)

    # source önce argümandan gelsin, yoksa config'den gelsin
    selected_source = args.source
    if selected_source is None:
        selected_source = cfg_get(cfg, "camera", "source", default="test")

    # --sim: donanımsız laptop testi için fail-open override
    if args.sim:
        log.warning("=" * 45)
        log.warning("SIM MODE ENABLED — donanim olmadan calisiyor")
        log.warning("Production icin --sim KULLANMA. Bu mod test/gelistirme icin.")
        log.warning("=" * 45)
        sim_camera_fallback = True
        sim_vehicle_fallback = True
    else:
        sim_camera_fallback = cfg_get(cfg, "camera", "allow_test_fallback", default=False)
        sim_vehicle_fallback = cfg_get(cfg, "vehicle", "allow_sim_fallback", default=False)

    # modüller
    camera = Camera(
        source=selected_source,
        width=cfg_get(cfg, "camera", "width", default=640),
        height=cfg_get(cfg, "camera", "height", default=480),
        fps=cfg_get(cfg, "camera", "fps", default=30),
        device_id=cfg_get(cfg, "camera", "device_id", default=0),
        allow_test_fallback=sim_camera_fallback,
    )

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
        allow_sim_fallback=sim_vehicle_fallback,
    )

    safety = SafetyMonitor(
        vehicle,
        warn_voltage=cfg_get(cfg, "safety", "battery_warn_voltage", default=13.0),
        critical_voltage=cfg_get(cfg, "safety", "battery_critical_voltage", default=12.0),
        watchdog_timeout=cfg_get(cfg, "safety", "watchdog_timeout", default=2.0),
        leak_pin=cfg_get(cfg, "safety", "leak_pin", default=17),
        leak_active_high=cfg_get(cfg, "safety", "leak_active_high", default=True),
    )

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

    ground = GroundStation(
        host=cfg_get(cfg, "ground_station", "host", default="192.168.2.1"),
        port=cfg_get(cfg, "ground_station", "port", default=14651),
        enabled=cfg_get(cfg, "ground_station", "enabled", default=True),
        send_interval_s=cfg_get(cfg, "ground_station", "send_interval_s", default=0.1),
    )

    video_sender = VideoSender(
        host=cfg_get(cfg, "video", "host", default="192.168.2.1"),
        port=cfg_get(cfg, "video", "port", default=14652),
        enabled=cfg_get(cfg, "video", "enabled", default=True),
        send_interval_s=cfg_get(cfg, "video", "send_interval_s", default=0.066),
        jpeg_quality=cfg_get(cfg, "video", "jpeg_quality", default=60),
        max_width=cfg_get(cfg, "video", "max_width", default=640),
    )

    command_rx = CommandReceiver(
        bind=cfg_get(cfg, "command", "bind", default="0.0.0.0"),
        port=cfg_get(cfg, "command", "port", default=14653),
        stale_after_s=cfg_get(cfg, "command", "stale_after_s", default=0.5),
    )

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

    if not startup(vehicle):
        log.error("Sistem başlatılamadı. Çıkılıyor.")
        try:
            camera.close()
        except Exception:
            pass
        telemetry.close()
        try:
            ground.close()
            video_sender.close()
            command_rx.close()
        except Exception:
            pass
        sys.exit(1)

    # Mod takibi: command receiver istek getirir, FSM'i ona gore set ederiz.
    current_mode = "auto"

    # Slew rate icin onceki PWM cikislari (ESC inrush koruma).
    prev_yaw_cmd = 0
    prev_fwd_cmd = 0
    prev_vrt_cmd = 0
    last_motor_t = time.time()

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

            # Stale link'te (laptop dustu) zorla auto'ya don. ROV otonom
            # kalir, motor sifirlanmaz — FSM SEARCH dondurur, gorev devam.
            if stale and current_mode != "auto":
                log.warning("Komut linki stale. Otonoma donuluyor.")
                current_mode = "auto"
                fsm.set_auto()
                yaw_pid.reset()
            elif requested_mode != current_mode:
                current_mode = requested_mode
                if current_mode == "manual":
                    fsm.set_manual()
                    yaw_pid.reset()
                    log.info("Mod -> MANUAL (yer istasyonu istegi)")
                else:
                    fsm.set_auto()
                    yaw_pid.reset()
                    log.info("Mod -> AUTO (yer istasyonu istegi)")

            emergency_cmd = bool(cmd.get("emergency_stop", False))

            # ---------------- FRAME ----------------
            frame = camera.read()

            if frame is None:
                frame_loss_count += 1
                log.warning(f"Frame alınamadı ({frame_loss_count}/{max_frame_loss})")

                if frame_loss_count >= max_frame_loss:
                    log.error("Art arda çok fazla frame kaybı oldu. Sistem durduruluyor.")
                    break

                time.sleep(0.01)
                continue

            frame_loss_count = 0

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

                safety_status = safety.check(sensor)

                if safety_status.get("emergency", False):
                    log.critical(safety_status.get("reason", "Acil durum"))
                    vehicle.stop()
                    break

                for warning in safety_status.get("warnings", []):
                    log.warning(warning)

            # ---------------- BORU TESPİT ----------------
            try:
                detection = detector.detect(frame)
            except Exception as e:
                log.error(f"Tespit hatası: {e}")
                detection = default_detection(frame)

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
                action = {
                    "state": "LOST",
                    "search_yaw": 150,
                    "forward_speed": 0,
                    "yaw_enabled": False,
                    "forward_enabled": False,
                    "message": "FSM fallback",
                }

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
            now_motor = time.time()
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
                    "voltage": float(sensor.get("voltage", 0.0)) if sensor else 0.0,
                    "heading": int(sensor.get("heading", 0)) if sensor else 0,
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

    finally:
        log.info("Temiz kapanış başlatıldı...")

        try:
            safety.cleanup()
        except Exception as e:
            log.error(f"Safety cleanup hatası: {e}")

        
        try:
            vehicle.send_rc(yaw=0, forward=0, vertical=0)
        except Exception:
            pass

        try:
            vehicle.stop()
            vehicle.disarm()
            vehicle.disconnect()
        except Exception as e:
            log.error(f"Araç kapanışında hata: {e}")

        try:
            camera.close()
        except Exception as e:
            log.error(f"Kamera kapanışında hata: {e}")

        telemetry.close()
        try:
            ground.close()
        except Exception as e:
            log.error(f"Ground station kapanis hatasi: {e}")
        try:
            video_sender.close()
        except Exception as e:
            log.error(f"Video sender kapanis hatasi: {e}")
        try:
            command_rx.close()
        except Exception as e:
            log.error(f"Command receiver kapanis hatasi: {e}")
        cv2.destroyAllWindows()
        log.info("Çakabey AUV kapatıldı.")


if __name__ == "__main__":
    main()