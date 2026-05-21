# Çakabey AUV Mert Sarıcı

**TEKNOCAK 2026** insansız sualtı aracı (ROV) yazılımı.

Tek bir kameradan boruyu algılar, FSM ile arar/yaklaşır/takip eder, PID ile merkezde tutar; donanım güvenliğini (pil / sızıntı / sensör watchdog) ayrı bir döngüde izler ve telemetriyi kara istasyonuna UDP üzerinden gönderir.

> **Durum:** Tasarım ve tezgâh testi aşaması. Havuz testleri henüz yapılmadı; parametreler sentetik veri ve SITL üzerinde optimize edildi, gerçek araç dinamiği ölçüldüğünde tekrar tune edilecek.

## Mimari

```
            ┌──────────┐
            │  camera  │  (CSI / webcam / test)
            └─────┬────┘
                  │ frame
                  ▼
          ┌───────────────┐      ┌──────────────────┐
          │ pipe_detector │      │ anomaly_detector │  (yosun/pas/kopma)
          └───────┬───────┘      └──────────────────┘
                  │ bbox
                  ▼
            ┌──────────┐         ┌──────────────┐
            │   fsm    │◄────────│ command_link │  (manuel komut, UDP)
            └─────┬────┘         └──────────────┘
                  │ hedef
                  ▼
        ┌─────────────────┐
        │ pid_controller  │  (yaw)
        └────────┬────────┘
                 │ PWM
                 ▼
            ┌─────────┐         ┌─────────────────┐
            │ vehicle │◄────────│ safety (leak,   │
            │ MAVLink │         │ batarya, wd)    │
            └─────────┘         └─────────────────┘
                 │
                 ▼
   ┌──────────────────────────────┐
   │ telemetry_logger (CSV)       │
   │ ground_station   (UDP/JSON)  │
   │ video_sender     (UDP/MJPEG) │
   └──────────────────────────────┘
```

## Modüller

| Dosya | İş |
|---|---|
| `main.py` | Ana kontrol döngüsü |
| `camera.py` | OpenCV/GStreamer kamera arayüzü |
| `pipe_detector.py` | HSV tabanlı boru tespiti |
| `anomaly_detector.py` | Yosun / pas / çatlak / kopma / eksik parça |
| `fsm.py` | `SEARCH → APPROACH → TRACK → LOST` (+ `MANUAL`) |
| `pid_controller.py` | Yaw PID (anti-windup, output clamp) |
| `vehicle.py` | Pixhawk MAVLink + sim fallback |
| `safety.py` | Pil / sızıntı (GPIO) / watchdog |
| `distance.py` | Pinhole veya paralel-lazer mesafe |
| `ground_station.py` / `ground_viewer.py` | Kara istasyonu telemetri (UDP/JSON) |
| `video_sender.py` / `video_viewer.py` | UDP MJPEG video stream |
| `command_link.py` / `manual_input.py` | Yer → ROV manuel komut kanalı |
| `telemetry_logger.py` | CSV log |
| `debug_overlay.py` | Görsel overlay (state, FPS, bbox, anomali) |

### Tuning araçları
| Dosya | İş |
|---|---|
| `abc_optimizer.py` | Yapay arı kolonisi (ABC) algoritması, `seed=42`, warm-start destekli |
| `abc_pid.py`, `tune_pid.py` | PID gain'lerini plant modeli üzerinde optimize eder |
| `abc_hsv.py`, `tune_hsv.py` | HSV eşiklerini etiketli görüntülerden optimize eder |
| `evaluator_pid.py`, `evaluator_hsv.py`, `evaluator_anomaly.py` | Performans metrikleri |

## Donanım

- **Frame:** BlueROV2 (standart, Heavy değil)
- **Otopilot:** Pixhawk + ArduSub (MAVLink)
- **İşlemci:** Jetson (CSI kamera için `nvarguscamerasrc` pipeline'ı mevcut)
- **Kamera:** 1280×720 @ 60fps, 720p downscale
- **Mesafe:** Pinhole (boru genişliği) veya paralel lazer (piksel boşluğu)
- **Sızıntı:** Jetson GPIO pin 17 (aktif-high)
- **Tether:** CAT6, BlueROV2 standart IP (192.168.2.1)

## Kurulum

```bash
git clone https://github.com/msarici/cakabey-auv.git
cd cakabey-auv
pip install -r requirements.txt
```

Sızıntı sensörü için Jetson'da ek olarak:

```bash
sudo apt install python3-jetson-gpio
```

> Geliştirme makinelerinde `Jetson.GPIO` import hatası verirse sızıntı sensörü pasif olur, yazılım çalışmaya devam eder (`safety` warning üretir).

## Çalıştırma

```bash
python main.py
```

Konfigürasyon `config.yaml` üzerinden. SITL ile tezgâh testi için:

```yaml
vehicle:
  connection: "udp:127.0.0.1:14551"
  allow_sim_fallback: false
camera:
  source: "test"
```

Gerçek araç:

```yaml
vehicle:
  connection: "/dev/ttyACM0"
camera:
  source: "csi"
```

## Test

```bash
python -m pytest tests/ -v
```

Test kapsamı: PID, FSM, safety, vehicle (sim), distance, anomaly, ground station, command link, video sender.

## Telemetri kanalları (default portlar)

| Kanal | Port | Format |
|---|---|---|
| Pixhawk MAVLink | 14551 | UDP |
| Telemetri (ROV → yer) | 14651 | UDP / JSON |
| Video (ROV → yer) | 14652 | UDP / MJPEG |
| Komut (yer → ROV) | 14653 | UDP / JSON |

## Lisans

MIT — bkz. [LICENSE](LICENSE).
