"""Hardware-free failure injection through startup and the actual main loop."""
from unittest.mock import Mock
import time
import pytest
import main
import safety
import vehicle


@pytest.fixture
def gpio(monkeypatch):
    gpio = Mock(BCM=11, IN=1, PUD_DOWN=2, PUD_UP=3, HIGH=1, LOW=0)
    gpio.input.return_value = 0
    monkeypatch.setattr(safety, 'GPIO', gpio, raising=False)
    monkeypatch.setattr(safety, 'GPIO_OK', True)
    return gpio


@pytest.mark.parametrize('failure', ['init', 'read', 'leak'])
def test_sensor_fault_prevents_arm(monkeypatch, gpio, failure):
    if failure == 'init':
        gpio.setup.side_effect = OSError('setup failed')
    elif failure == 'read':
        gpio.input.side_effect = OSError('read failed')
    else:
        gpio.input.return_value = 1
    veh = Mock()
    mon = safety.SafetyMonitor(veh, leak_pin=17)
    assert main.startup(veh, mon) is False
    veh.connect.assert_not_called()
    veh.arm.assert_not_called()


def test_heartbeat_timeout_is_failed_connection(monkeypatch):
    master = Mock()
    master.wait_heartbeat.return_value = None
    monkeypatch.setattr(vehicle.mavutil, 'mavlink_connection', Mock(return_value=master))
    veh = vehicle.Vehicle()
    assert not main.startup(veh)
    assert not veh.sim_mode
    assert not veh.armed
    master.arducopter_arm.assert_not_called()


def test_missing_mavlink_cannot_enable_simulation(monkeypatch):
    monkeypatch.setattr(vehicle, 'MAVLINK_OK', False)
    veh = vehicle.Vehicle()
    assert not main.startup(veh)
    assert not veh.sim_mode
    assert veh.read_sensors() is None


def prepare_main(monkeypatch, sim, veh):
    cfg = {'vehicle': {'allow_sim_fallback': True}, 'safety': {'leak_pin': 17, 'max_sensor_loss': 2},
           'camera': {'max_frame_loss': 1}}
    monkeypatch.setattr(main, 'load_config', lambda _: cfg)
    monkeypatch.setattr(main.sys, 'argv', ['main.py', '--no-display'] + (['--sim'] if sim else []))
    factory = Mock(return_value=veh)
    monkeypatch.setattr(main, 'Vehicle', factory)
    camera = Mock()
    camera.read.return_value = None
    monkeypatch.setattr(main, 'Camera', Mock(return_value=camera))
    for name in ['TelemetryLogger', 'GroundStation', 'VideoSender', 'CommandReceiver']:
        monkeypatch.setattr(main, name, Mock())
    main.CommandReceiver.return_value.get_command.return_value = ({'mode': 'auto'}, False)
    return factory, camera


def test_legacy_yaml_true_does_not_allow_hardware_fallback(monkeypatch, gpio):
    veh = Mock()
    veh.connect.return_value = False
    # Capture actual constructor flags while using real Vehicle behavior.
    real_vehicle = vehicle.Vehicle
    def factory(**kwargs):
        kwargs.pop("supervisor_timeout")  # Factory isolates transport in this test.
        v = real_vehicle(**kwargs)
        monkeypatch.setattr(v, 'connect', lambda: False)
        assert v.allow_sim_fallback is False
        assert v.simulation is False
        return v
    prepare_main(monkeypatch, False, veh)
    monkeypatch.setattr(main, 'Vehicle', factory)
    with pytest.raises(SystemExit) as exit_info:
        main.main()
    assert exit_info.value.code == 1


def test_main_explicit_simulation_bypasses_gpio_and_pixhawk(monkeypatch, gpio):
    veh = vehicle.Vehicle(simulation=True)
    factory, camera = prepare_main(monkeypatch, True, veh)
    connect = Mock(side_effect=AssertionError('hardware accessed'))
    monkeypatch.setattr(vehicle.mavutil, 'mavlink_connection', connect)
    main.main()
    assert factory.call_args.kwargs['simulation'] is True
    assert factory.call_args.kwargs['allow_sim_fallback'] is False
    connect.assert_not_called()
    gpio.setup.assert_not_called()
    gpio.input.assert_not_called()
    assert not veh.armed  # orderly shutdown
    assert veh.last_rc == {'yaw': 0, 'forward': 0, 'vertical': 0}


@pytest.mark.parametrize('failure', ['read', 'leak', 'connection', 'stale'])
def test_main_runtime_failure_stops_and_disarms_even_without_camera(monkeypatch, gpio, failure):
    veh = Mock(sim_mode=False, allow_sim_fallback=False, flight_mode='MANUAL')
    fresh = {'voltage': 14, 'timestamp': time.monotonic(), 'heading': None}
    if failure == 'read':
        gpio.input.side_effect = [0, 0, 0, OSError('GPIO lost')]
    elif failure == 'leak':
        gpio.input.side_effect = [0, 0, 0, 1]
    stale = dict(fresh, timestamp=time.monotonic()-10)
    veh.read_sensors.side_effect = [fresh, fresh] + ([None, None] if failure == 'connection' else
                                            [stale] if failure == 'stale' else [fresh])
    _, camera = prepare_main(monkeypatch, False, veh)
    main.main()
    veh.stop.assert_called()
    veh.disarm.assert_called_once()
    veh.disconnect.assert_called_once()
    camera.read.assert_not_called()  # safety runs before camera


def test_real_vehicle_read_exception_never_becomes_simulation():
    veh = vehicle.Vehicle()
    veh.master = Mock()
    veh.master.recv_match.side_effect = OSError('serial disconnected')
    assert veh.read_sensors() is None
    assert not veh.sim_mode
    # Stop/disarm remain real MAVLink requests, never simulated success.
    assert veh.stop()
    assert not veh.disarm()  # Request sent; disconnected hardware cannot confirm.
    veh.master.mav.rc_channels_override_send.assert_called_once()
    veh.master.arducopter_disarm.assert_called_once()


def test_cached_telemetry_connection_loss_preserves_watchdog(monkeypatch):
    veh = vehicle.Vehicle()
    veh.master = Mock()
    veh.master.recv_match.return_value = None
    veh._cached_voltage = 14
    veh._last_voltage_time = time.monotonic() - 5
    mon = safety.SafetyMonitor(veh, leak_pin=None, watchdog_timeout=2)
    status = mon.check(veh.read_sensors())
    assert status['emergency']
    assert status['reason'] == 'Sensör zaman aşımı'
    assert not veh.sim_mode


def test_normal_simulation_processes_a_frame_and_shuts_down(monkeypatch, gpio):
    import numpy as np
    veh = vehicle.Vehicle(simulation=True)
    _, camera = prepare_main(monkeypatch, True, veh)
    camera.read.side_effect = [np.zeros((480, 640, 3), dtype=np.uint8), KeyboardInterrupt]
    main.main()
    assert camera.read.call_count == 2
    main.TelemetryLogger.return_value.log.assert_called_once()
    assert not veh.armed
    gpio.input.assert_not_called()


def test_failed_heartbeat_closes_serial_port(monkeypatch):
    master = Mock()
    master.wait_heartbeat.return_value = None
    monkeypatch.setattr(vehicle.mavutil, 'mavlink_connection', Mock(return_value=master))
    veh = vehicle.Vehicle()
    assert not veh.connect()
    master.close.assert_called_once()
    assert veh.master is None
