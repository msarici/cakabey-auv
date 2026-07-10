# Çakabey Underwater Robotics Software

[![Tests](https://github.com/msarici/cakabey-auv/actions/workflows/tests.yml/badge.svg)](https://github.com/msarici/cakabey-auv/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

A modular Python software prototype for a tethered underwater vehicle, developed for the **TEKNOCAK 2026** competition.

The stack combines OpenCV-based visual detection, autonomous state control, PID steering, Pixhawk/ArduSub communication, remote commands, telemetry, video streaming, safety monitoring, and simulation support.

## Result and responsibility

- **Team result:** 3rd place at TEKNOCAK 2026
- **My role:** Software Team Lead
- **My scope:** software architecture, computer vision, autonomous control logic, PID steering, MAVLink integration, telemetry, remote commands, safety logic, simulation support, and automated tests

## Validation status

The software was evaluated with automated tests, synthetic camera input, simulated vehicle connections, and bench-level development.

**Full in-water autonomous validation was not completed** because the vehicle's mechanical and electrical subsystems were not ready for safe pool testing. This repository documents the completed software engineering work and does not claim successful underwater autonomous operation.

## Core capabilities

- HSV-based pipe detection with OpenCV
- `SEARCH → APPROACH → TRACK → LOST` autonomous state machine
- Manual and autonomous operating modes
- PID yaw control with anti-windup and output limiting
- Pixhawk and ArduSub communication through MAVLink
- Battery, sensor-watchdog, frame-loss, and leak-monitoring logic
- UDP telemetry and remote command channels
- UDP/MJPEG video streaming
- CSV telemetry logging and visual debugging overlays
- Simulation fallbacks for development without vehicle hardware
- Artificial Bee Colony tuning tools for PID and HSV parameters
- Automated tests for control, safety, communication, and vehicle modules

## Architecture

```text
            ┌──────────┐
            │  camera  │  CSI / webcam / synthetic input
            └─────┬────┘
                  │ frame
                  ▼
          ┌───────────────┐      ┌──────────────────┐
          │ pipe_detector │      │ anomaly_detector │
          └───────┬───────┘      └──────────────────┘
                  │ detection
                  ▼
            ┌──────────┐         ┌──────────────┐
            │   FSM    │◄────────│ command_link │  manual commands / UDP
            └─────┬────┘         └──────────────┘
                  │ target action
                  ▼
        ┌─────────────────┐
        │ pid_controller  │  yaw control
        └────────┬────────┘
                 │ PWM offset
                 ▼
            ┌─────────┐         ┌─────────────────┐
            │ vehicle │◄────────│ safety monitor  │
            │ MAVLink │         │ battery/leak/wd │
            └────┬────┘         └─────────────────┘
                 │
                 ▼
   ┌────────────────────────────────┐
   │ telemetry_logger   CSV         │
   │ ground_station     UDP / JSON  │
   │ video_sender       UDP / MJPEG │
   └────────────────────────────────┘
```

## Main modules

| File | Responsibility |
|---|---|
| `main.py` | Main control loop and subsystem orchestration |
| `camera.py` | OpenCV/GStreamer camera interface |
| `pipe_detector.py` | HSV-based pipe detection |
| `anomaly_detector.py` | Algae, rust, crack, break, and missing-part heuristics |
| `fsm.py` | Autonomous and manual operating states |
| `pid_controller.py` | Yaw PID with anti-windup and output limits |
| `vehicle.py` | Pixhawk/MAVLink communication and simulation fallback |
| `safety.py` | Battery, leak GPIO, and sensor-watchdog monitoring |
| `distance.py` | Pinhole or parallel-laser distance estimation |
| `ground_station.py` / `ground_viewer.py` | UDP/JSON telemetry channel |
| `video_sender.py` / `video_viewer.py` | UDP/MJPEG video channel |
| `command_link.py` / `manual_input.py` | Ground-to-vehicle command channel |
| `telemetry_logger.py` | CSV telemetry logging |
| `debug_overlay.py` | Runtime state, FPS, detection, and anomaly overlays |

### Tuning and evaluation

| File | Responsibility |
|---|---|
| `abc_optimizer.py` | Reproducible Artificial Bee Colony optimizer with warm start |
| `abc_pid.py`, `tune_pid.py` | PID gain optimization against a plant model |
| `abc_hsv.py`, `tune_hsv.py` | HSV threshold optimization using labeled images |
| `evaluator_pid.py`, `evaluator_hsv.py`, `evaluator_anomaly.py` | Evaluation metrics |

## Technology stack

- Python 3.10+
- OpenCV and NumPy
- pymavlink
- Pixhawk and ArduSub
- NVIDIA Jetson / embedded Linux
- UDP, JSON, and MJPEG
- pytest

## Quick start

```bash
git clone https://github.com/msarici/cakabey-auv.git
cd cakabey-auv
python -m venv .venv
```

Activate the environment:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run without vehicle hardware

The explicit `--sim` flag enables synthetic camera input and vehicle simulation fallback:

```bash
python main.py --sim
```

Run without the OpenCV display window:

```bash
python main.py --sim --no-display
```

> Simulation mode is for development and demonstration. It must not be used as a substitute for hardware validation.

## Configuration

Runtime settings are stored in `config.yaml`.

Example SITL connection:

```yaml
vehicle:
  connection: "udp:127.0.0.1:14551"
  allow_sim_fallback: false
camera:
  source: "test"
```

Example physical connection:

```yaml
vehicle:
  connection: "/dev/ttyACM0"
camera:
  source: "csi"
```

Jetson leak-sensor support additionally requires:

```bash
sudo apt install python3-jetson-gpio
```

When `Jetson.GPIO` is unavailable, the leak input is disabled and the safety module emits a warning.

## Tests

Run the full test suite:

```bash
python -m pytest tests/ -v
```

The suite covers PID control, FSM transitions, startup behavior, safety monitoring, simulated vehicle communication, distance estimation, anomaly logic, ground-station communication, manual commands, and video transport.

GitHub Actions runs the test suite on every push and pull request.

## Default network channels

| Channel | Port | Format |
|---|---:|---|
| Pixhawk MAVLink | 14551 | UDP |
| Vehicle → ground telemetry | 14651 | UDP / JSON |
| Vehicle → ground video | 14652 | UDP / MJPEG |
| Ground → vehicle commands | 14653 | UDP / JSON |

## Hardware target

- BlueROV2-style standard frame
- Pixhawk running ArduSub
- NVIDIA Jetson with CSI camera support
- 1280×720 camera input with runtime downscaling
- Optional pinhole or parallel-laser distance estimation
- Optional active-high leak input on Jetson GPIO pin 17
- CAT6 tether and BlueROV2-style network layout

## Known limitations

- No completed in-water autonomous validation
- Control parameters require retuning against measured vehicle dynamics
- The anomaly detector uses classical image-processing heuristics rather than a trained model
- Leak monitoring requires physical Jetson GPIO integration
- Safety-critical deployment requires additional hardware-in-the-loop and field testing

## Author

**Mert Sarıcı** — software architecture and implementation

## License

Released under the [MIT License](LICENSE).