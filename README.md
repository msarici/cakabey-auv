# Cakabey AUV — Autonomous Underwater Robotics Stack

[![Tests](https://github.com/msarici/cakabey-auv/actions/workflows/tests.yml/badge.svg)](https://github.com/msarici/cakabey-auv/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green)
![MAVLink](https://img.shields.io/badge/MAVLink-Pixhawk-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

Autonomy, computer-vision, control, telemetry, and safety stack for the **Cakabey underwater robotics project** — **3rd place nationally, TEKNOCAK 2026** (Ankara, Turkey).

I was the Software Team Lead and sole developer: I designed and implemented the complete architecture — vision, autonomous behavior, PID control, Pixhawk/MAVLink integration, safety monitoring, telemetry, remote command, simulation support, optimization tooling, and automated tests. The system runs as a multi-module Python application on an NVIDIA Jetson companion computer, talking to a Pixhawk running ArduSub.

**Validation:** automated unit/integration tests, ArduSub SITL, synthetic and labeled-frame evaluation, and Jetson/Pixhawk bench integration.

---

## What it does

1. Captures video from a CSI camera, webcam, or synthetic test source
2. Detects a target pipe via HSV segmentation, contour filtering, and bounding-box geometry
3. Estimates distance (known-width pinhole model or parallel-laser pixel separation)
4. Selects behavior through a finite-state machine: `SEARCH → APPROACH → TRACK → LOST` (+ `MANUAL`)
5. Keeps the target centered with PID yaw control (anti-windup, output clamping, slew-rate limiting)
6. Sends RC override commands to the Pixhawk over MAVLink
7. Monitors battery, leak input (Jetson GPIO), sensor freshness, frame loss, and command-link health before every motor output
8. Streams UDP/JSON telemetry and UDP/MJPEG video to the ground station; logs runs to CSV

An experimental classical-CV anomaly detector flags algae, rust, cracks, breaks, and missing pipe sections.

---

## Architecture

```text
                         ┌─────────────────────┐
                         │       Camera        │
                         │ CSI / Webcam / Test │
                         └──────────┬──────────┘
                                    │ frame
                                    ▼
                     ┌──────────────────────────┐
                     │      Pipe Detector       │
                     │ HSV / contours / bbox    │
                     └─────────────┬────────────┘
                                   │ detection
                  ┌────────────────┴────────────────┐
                  ▼                                 ▼
       ┌─────────────────────┐          ┌─────────────────────┐
       │  Anomaly Detector   │          │ Distance Estimator  │
       │ algae/rust/cracks   │          │ pinhole / lasers    │
       └─────────────────────┘          └─────────────────────┘
                                   │
                                   ▼
                     ┌──────────────────────────┐
                     │   Finite-State Machine   │
                     │ SEARCH / APPROACH /      │
                     │ TRACK / LOST / MANUAL    │
                     └─────────────┬────────────┘
                                   │ target action
                                   ▼
                     ┌──────────────────────────┐
                     │      PID Controller      │
                     └─────────────┬────────────┘
                                   │ PWM offsets
                                   ▼
        ┌────────────────────┐  ┌────────────────────┐
        │   Safety Monitor   │─▶│ Vehicle Interface  │
        │ battery / leak /   │  │ Pixhawk / MAVLink  │
        │ watchdog / faults  │  │ ArduSub / RC       │
        └────────────────────┘  └──────────┬─────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
       ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
       │ Telemetry Logger   │  │  Ground Station    │  │   Video Sender     │
       │ CSV                │  │ UDP / JSON         │  │ UDP / MJPEG        │
       └────────────────────┘  └────────────────────┘  └────────────────────┘
                                           ▲
                                           │ manual commands
                                  ┌────────┴─────────┐
                                  │  Command Link    │
                                  └──────────────────┘
```

---

## Modules

| File | Responsibility |
| --- | --- |
| `main.py` | Main runtime loop and subsystem orchestration |
| `camera.py` | CSI, webcam, GStreamer, and synthetic camera input |
| `pipe_detector.py` | HSV-based pipe detection and target geometry |
| `anomaly_detector.py` | Experimental anomaly-detection heuristics |
| `fsm.py` | Autonomous and manual state transitions |
| `pid_controller.py` | PID yaw control, anti-windup, output limits |
| `vehicle.py` | Pixhawk/MAVLink integration and simulation fallback |
| `safety.py` | Battery, watchdog, leak-input, emergency monitoring |
| `distance.py` | Pinhole and parallel-laser distance estimation |
| `ground_station.py` / `ground_viewer.py` | UDP/JSON telemetry send + ground-side viewer |
| `video_sender.py` / `video_viewer.py` | UDP/MJPEG video send + ground-side viewer |
| `command_link.py` / `manual_input.py` | Surface → vehicle manual command channel |
| `telemetry_logger.py` | Runtime CSV logging |
| `debug_overlay.py` | Detection, state, FPS, command, anomaly overlay |

**Tuning tools:** `abc_optimizer.py` (Artificial Bee Colony, seeded runs, warm start), `abc_pid.py` / `tune_pid.py` / `evaluator_pid.py` (PID gains against a plant model), `abc_hsv.py` / `tune_hsv.py` / `tune_hsv_live.py` / `evaluator_hsv.py` (HSV thresholds from labeled frames, plus live trackbar tuning), `evaluator_anomaly.py`.

---

## Engineering decisions

**Classical CV instead of deep learning.** HSV segmentation with geometric filtering needs no training pipeline, retunes in minutes for new lighting/water conditions, runs deterministically at full camera rate on the Jetson, and fails in ways you can inspect. For a constrained underwater target, this beats a neural network on every axis that mattered.

**ABC optimization instead of manual tuning.** Hand-tuning HSV thresholds and PID gains per pool doesn't scale. The Artificial Bee Colony optimizer converges on both from labeled frames and a plant model, with seeded, reproducible runs and warm-start support.

**FSM instead of monolithic control logic.** Explicit states make target-loss behavior safe, manual/autonomous handover clean, and every transition unit-testable.

**Safety before motor output.** Battery, leak, sensor-watchdog, frame-loss, and command-link checks run before any motor command in every control-loop iteration. Emergency conditions neutralize the commanded axes immediately. Stale manual links automatically fall back to autonomous mode instead of executing old commands.

**Simulation fallback built in.** Every hardware dependency — Pixhawk, CSI camera, GPIO leak sensor — has an explicit development fallback, so the full stack runs and tests on a machine with no vehicle attached.

---

## Hardware target

| Component | Detail |
| --- | --- |
| Vehicle frame | BlueROV2-style standard frame |
| Autopilot | Pixhawk running ArduSub |
| Companion computer | NVIDIA Jetson (CSI camera via GStreamer / `nvarguscamerasrc`) |
| Leak input | Jetson GPIO, active-high |
| Tether | Cat6 Ethernet; serial or UDP MAVLink |

---

## Setup and running

```bash
git clone https://github.com/msarici/cakabey-auv.git
cd cakabey-auv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install python3-jetson-gpio   # Jetson only; leak input disabled elsewhere
```

Without hardware:

```bash
python main.py --sim --no-display
```

SITL (`config.yaml`):

```yaml
vehicle:
  connection: "udp:127.0.0.1:14551"
  allow_sim_fallback: false
camera:
  source: "test"
```

Physical vehicle:

```yaml
vehicle:
  connection: "/dev/ttyACM0"
  baudrate: 115200
camera:
  source: "csi"
```

---

## Tests

```bash
python -m pytest tests/ -v
```

Covers PID behavior (saturation, anti-windup, reset, invalid parameters), FSM transitions, mode handover, safety thresholds, simulated vehicle communication, distance estimation, anomaly detection, ground-station and command-link handling, and video transport. GitHub Actions runs the suite on every push and pull request.

---

## Default network channels

| Channel | Port | Format |
| --- | ---: | --- |
| Pixhawk MAVLink | `14551` | UDP |
| Vehicle → ground telemetry | `14651` | UDP / JSON |
| Vehicle → ground video | `14652` | UDP / MJPEG |
| Ground → vehicle commands | `14653` | UDP / JSON |

---

## Known limitations

* PID gains and HSV thresholds require retuning against the physical vehicle and water conditions before operation
* The anomaly detector is heuristic, not a trained model
* UDP telemetry/command transport assumes a controlled tethered network — no authentication or encryption
* Single-process runtime; may be split into services in a future revision

---

## Author

**Mert Sarıcı** — Software Team Lead and sole developer of the Cakabey autonomy stack.

Available for freelance work: ArduPilot/ArduSub · MAVLink · NVIDIA Jetson · OpenCV · robotics control · telemetry systems · embedded Python integration and debugging.

**Upwork:** _profile link here once live_

---

## License

[MIT](LICENSE)
