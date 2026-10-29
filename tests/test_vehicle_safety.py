"""Deterministic MAVLink failure injection; no serial device required."""
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import vehicle as module
from vehicle import Vehicle
from safety import SafetyMonitor


class Message:
    def __init__(self, kind, source=(1, 1), **fields):
        self.kind, self.source = kind, source
        self.__dict__.update(fields)

    def get_type(self):
        return self.kind

    def get_srcSystem(self):
        return self.source[0]

    def get_srcComponent(self):
        return self.source[1]


def heartbeat(armed=False, mode=0, source=(1, 1)):
    return Message('HEARTBEAT', source, base_mode=128 if armed else 0,
                   custom_mode=mode, autopilot=3, type=12)


@pytest.fixture
def clock(monkeypatch):
    state = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: state[0])
    monkeypatch.setattr(module.time, 'sleep', lambda amount: state.__setitem__(0, state[0]+amount))
    return state


@pytest.fixture
def connected(clock):
    v = Vehicle(heartbeat_timeout=0.03)
    v._target = (1, 1)
    v._handle_message(heartbeat())
    messages = deque()
    v.master = Mock(target_system=1, target_component=1)
    v.master.recv_match.side_effect = lambda **kwargs: messages.popleft() if messages else None
    v.master.mode_mapping.return_value = {'MANUAL': 0, 'ALT_HOLD': 2}
    return v, messages


def test_arm_requires_fresh_confirming_heartbeat(connected):
    v, messages = connected
    assert not v.arm()
    assert not v.armed
    messages.append(heartbeat(armed=True))
    assert v.arm()
    assert v.armed


def test_arm_denied_by_heartbeat_does_not_report_success(connected):
    v, messages = connected
    messages.append(heartbeat(armed=False))
    assert not v.arm()


def test_disarm_denied_does_not_report_disarmed(connected):
    v, messages = connected
    v.armed = True
    messages.append(heartbeat(armed=True))
    assert not v.disarm()
    assert v.armed
    messages.append(heartbeat(armed=False))
    assert v.disarm()
    assert not v.armed


def test_mode_needs_confirmed_custom_mode(connected):
    v, messages = connected
    messages.append(heartbeat(mode=0))
    assert not v.set_mode('ALT_HOLD')
    messages.append(heartbeat(mode=2))
    assert v.set_mode('ALT_HOLD')


def test_foreign_heartbeat_cannot_confirm_arm(connected):
    v, messages = connected
    messages.append(heartbeat(armed=True, source=(2, 1)))
    assert not v.arm()


@pytest.mark.parametrize('source', [(2, 1), (1, 42)])
def test_foreign_telemetry_cannot_refresh_watchdog(connected, clock, source):
    v, messages = connected
    messages.append(Message('SYS_STATUS', voltage_battery=14000))
    assert v.read_sensors()['timestamp'] == 100
    clock[0] = 110
    messages.append(Message('SYS_STATUS', source=source, voltage_battery=16000))
    data = v.read_sensors()
    assert data['voltage'] == 14
    assert data['timestamp'] == 100
    assert SafetyMonitor(v).check(data)['emergency']


@pytest.mark.parametrize('voltage', [65535, 0, -1, float('nan'), float('inf'), None])
def test_unknown_or_invalid_voltage_clears_cached_good_value(connected, voltage):
    v, messages = connected
    messages.append(Message('SYS_STATUS', voltage_battery=14000))
    assert v.read_sensors()['voltage'] == 14
    messages.append(Message('SYS_STATUS', voltage_battery=voltage))
    assert v.read_sensors() is None


def test_fresh_voltage_does_not_hide_heartbeat_loss(connected, clock):
    v, messages = connected
    clock[0] = 110
    messages.append(Message('SYS_STATUS', voltage_battery=14000))
    status = SafetyMonitor(v).check(v.read_sensors())
    assert status['emergency']
    assert status['reason'] == 'Heartbeat zaman aşımı'


def test_reconnect_clears_old_telemetry(monkeypatch, connected):
    v, _ = connected
    old_master = v.master
    v._cached_voltage, v._last_voltage_time = 14, 100
    new_master = Mock()
    new_master.wait_heartbeat.return_value = heartbeat()
    new_master.recv_match.return_value = None
    monkeypatch.setattr(module.mavutil, 'mavlink_connection', lambda *a, **kw: new_master)
    monkeypatch.setattr(v, '_warm_up_sensors', lambda **kw: None)
    assert v.connect()
    assert v.read_sensors() is None
    old_master.close.assert_called_once()


def test_ground_station_heartbeat_is_not_pixhawk(monkeypatch, clock):
    master = Mock()
    hb = heartbeat()
    hb.autopilot, hb.type = 8, 6
    master.wait_heartbeat.return_value = hb
    monkeypatch.setattr(module.mavutil, 'mavlink_connection', lambda *a, **kw: master)
    v = Vehicle()
    assert not v.connect()
    master.close.assert_called_once()
    assert not v.sim_mode


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf')])
def test_invalid_heartbeat_timeout_rejected(value):
    with pytest.raises(ValueError):
        Vehicle(heartbeat_timeout=value)


@pytest.mark.parametrize('voltage', [0, -1, float('nan'), float('inf'), None])
def test_bad_voltage_is_emergency(voltage):
    assert SafetyMonitor(None).check({'voltage': voltage})['emergency']


@pytest.mark.parametrize('stamp', [float('nan'), float('inf'), 200.0])
def test_bad_timestamp_cannot_bypass_watchdog(clock, stamp):
    assert SafetyMonitor(None).check({'voltage': 14, 'timestamp': stamp})['emergency']


@pytest.mark.parametrize('kwargs', [{'watchdog_timeout': 0}, {'watchdog_timeout': float('nan')},
                                    {'critical_voltage': 14, 'warn_voltage': 13}])
def test_bad_safety_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        SafetyMonitor(None, **kwargs)
