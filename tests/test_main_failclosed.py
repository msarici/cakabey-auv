"""Failure injection at the application boundary (no motors or network)."""
from unittest.mock import Mock
import math
import time
import numpy as np
import pytest
import main
from test_safety_integration import prepare_main, gpio


def vehicle_stub():
    veh = Mock(sim_mode=False, allow_sim_fallback=False, flight_mode='MANUAL')
    veh.read_sensors.side_effect = lambda: {'voltage': 14, 'timestamp': time.monotonic(), 'heading': None}
    return veh


def test_estop_precedes_camera_and_terminates(monkeypatch, gpio):
    veh = vehicle_stub()
    _, camera = prepare_main(monkeypatch, False, veh)
    main.CommandReceiver.return_value.get_command.return_value = ({'emergency_stop': True}, False)
    main.main()
    camera.read.assert_not_called()
    veh.send_rc.assert_not_called()
    veh.stop.assert_called()
    veh.disarm.assert_called_once()


def test_manual_link_loss_cannot_restart_auto(monkeypatch, gpio):
    veh = vehicle_stub()
    _, camera = prepare_main(monkeypatch, False, veh)
    camera.read.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    main.CommandReceiver.return_value.get_command.side_effect = [
        ({'mode': 'manual', 'fwd': 1}, False),
        ({'mode': 'manual', 'fwd': 1}, False), ({'mode': 'auto'}, True)]
    main.main()
    assert camera.read.call_count == 1
    assert veh.send_rc.call_count == 1
    veh.disarm.assert_called_once()


@pytest.mark.parametrize('component', ['PipeDetector', 'FSM'])
def test_processing_exception_stops_instead_of_searching(monkeypatch, gpio, component):
    veh = vehicle_stub()
    _, camera = prepare_main(monkeypatch, False, veh)
    camera.read.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    obj = Mock()
    (obj.detect if component == 'PipeDetector' else obj.update).side_effect = RuntimeError('processing failed')
    monkeypatch.setattr(main, component, Mock(return_value=obj))
    main.main()
    veh.send_rc.assert_not_called()
    veh.stop.assert_called()
    veh.disarm.assert_called_once()


def test_first_missing_camera_frame_requests_neutral(monkeypatch, gpio):
    veh = vehicle_stub()
    _, camera = prepare_main(monkeypatch, False, veh)
    main.main()
    assert veh.stop.call_count >= 2  # immediate frame failure plus shutdown
    veh.send_rc.assert_not_called()


def test_partial_startup_and_cleanup_failure_still_disarms(monkeypatch, gpio):
    veh = vehicle_stub()
    veh.arm.return_value = False
    veh.stop.side_effect = OSError('stop failed')
    _, camera = prepare_main(monkeypatch, False, veh)
    with pytest.raises(SystemExit):
        main.main()
    veh.disarm.assert_called_once()
    veh.disconnect.assert_called_once()
    camera.close.assert_called_once()
    main.TelemetryLogger.return_value.close.assert_called_once()


@pytest.mark.parametrize('value', [0, -1, math.nan, math.inf, True, '2'])
def test_invalid_watchdog_config_is_rejected(value):
    with pytest.raises(ValueError):
        main.validate_config({'safety': {'watchdog_timeout': value}})


def test_hardware_cannot_disable_leak_sensor():
    with pytest.raises(ValueError):
        main.validate_config({'safety': {'leak_pin': None}})
    main.validate_config({'safety': {'leak_pin': None}}, simulation=True)


def test_missing_config_stops_startup(tmp_path):
    with pytest.raises(FileNotFoundError):
        main.load_config(tmp_path/'missing.yaml')


def test_malformed_config_stops_startup(tmp_path):
    path = tmp_path/'config.yaml'
    path.write_text('- unexpected\n- list\n')
    with pytest.raises(ValueError):
        main.load_config(path)


def test_estop_arriving_during_frame_processing_prevents_output(monkeypatch, gpio):
    veh = vehicle_stub()
    _, camera = prepare_main(monkeypatch, False, veh)
    camera.read.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    main.CommandReceiver.return_value.get_command.side_effect = [
        ({'mode': 'auto'}, False), ({'emergency_stop': True}, False)]
    main.main()
    veh.send_rc.assert_not_called()
    veh.disarm.assert_called_once()


def test_stale_sample_after_processing_prevents_output(monkeypatch, gpio):
    veh = vehicle_stub()
    fresh = {'voltage': 14, 'timestamp': time.monotonic(), 'heading': None}
    veh.read_sensors.side_effect = None
    veh.read_sensors.return_value = fresh
    _, camera = prepare_main(monkeypatch, False, veh)
    camera.read.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    detector = Mock()
    def detect(frame):
        fresh['timestamp'] -= 10
        return main.default_detection(frame)
    detector.detect.side_effect = detect
    monkeypatch.setattr(main, 'PipeDetector', Mock(return_value=detector))
    main.main()
    veh.send_rc.assert_not_called()
    veh.disarm.assert_called_once()
