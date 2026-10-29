"""Real pymavlink codec tests plus mocked transport; no flight controller needed."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pymavlink import mavutil
from pymavlink.dialects.v20 import ardupilotmega as wire
from vehicle import Vehicle

KEY = bytes(range(32))  # Public test-only key; never used by application defaults.


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv('CAKABEY_MAVLINK_KEY', raising=False)
    # Any MAVLINK20 assignment by connect is restored at test exit.
    monkeypatch.setenv('MAVLINK20', '1')


def signed_receiver():
    vehicle = Vehicle()
    master = SimpleNamespace(mav=wire.MAVLink(None))
    master.setup_signing = Mock(side_effect=lambda *a, **kw: mavutil.mavfile.setup_signing(master, *a, **kw))
    vehicle.master = master
    vehicle._configure_signing(KEY)
    master.mav.signing.timestamp = 100
    return vehicle, master


def packet(key=KEY, stamp=101, system=1, component=1):
    sender = wire.MAVLink(None, srcSystem=system, srcComponent=component)
    sender.signing.secret_key = key
    sender.signing.sign_outgoing = key is not None
    sender.signing.link_id = 0
    sender.signing.timestamp = stamp
    hb = sender.heartbeat_encode(wire.MAV_TYPE_SUBMARINE, wire.MAV_AUTOPILOT_ARDUPILOTMEGA, 0, 0, 0)
    return hb.pack(sender)


def test_configure_signing_has_no_unsigned_exception():
    _, master = signed_receiver()
    master.setup_signing.assert_called_once_with(KEY, sign_outgoing=True, allow_unsigned_callback=None)
    assert master.mav.signing.sign_outgoing


@pytest.mark.parametrize('key', [None, bytes(reversed(range(32)))])
def test_unsigned_and_wrong_key_rejected_by_actual_decoder(key):
    _, master = signed_receiver()
    with pytest.raises(wire.MAVError, match='Invalid signature'):
        master.mav.parse_char(packet(key=key))


def test_real_decoder_accepts_authentic_packet_and_rejects_replay():
    _, master = signed_receiver()
    data = packet()
    msg = master.mav.parse_char(data)
    assert msg.get_type() == 'HEARTBEAT'
    assert msg.get_signed()
    with pytest.raises(wire.MAVError, match='Invalid signature'):
        master.mav.parse_char(data)


def test_bad_signature_cannot_poison_replay_timestamp():
    _, master = signed_receiver()
    assert master.mav.parse_char(packet(stamp=101)).get_signed()
    with pytest.raises(wire.MAVError, match='Invalid signature'):
        master.mav.parse_char(packet(key=b'x'*32, stamp=100000))
    assert master.mav.parse_char(packet(stamp=102)).get_signed()


@pytest.mark.parametrize('connection', ['udp:127.0.0.1:14550', 'udpin:0.0.0.0:14550',
                                         'tcp:localhost:5760', 'localhost:14550',
                                         'unix:/tmp/autopilot.sock', '/tmp/flight.tlog'])
def test_non_serial_transport_requires_key(connection, monkeypatch):
    open_transport = Mock()
    monkeypatch.setattr(mavutil, 'mavlink_connection', open_transport)
    vehicle = Vehicle(connection=connection)
    assert not vehicle.connect()
    assert not vehicle.sim_mode
    open_transport.assert_not_called()


@pytest.mark.parametrize('port', ['/dev/ttyACM0', '/dev/ttyUSB0', '/dev/serial/by-id/pixhawk', 'COM3'])
def test_unsigned_local_serial_is_explicit_supported_policy(port):
    assert Vehicle(connection=port)._load_signing_key() is None


def test_local_serial_can_require_signing():
    with pytest.raises(ValueError, match='required'):
        Vehicle(require_signing=True)._load_signing_key()


@pytest.mark.parametrize('key', ['x'*64, '00'*31, '00'*33, '  '+'00'*32])
def test_invalid_key_is_rejected_without_exposing_it(key, monkeypatch):
    monkeypatch.setenv('CAKABEY_MAVLINK_KEY', key)
    with pytest.raises(ValueError) as error:
        Vehicle()._load_signing_key()
    assert key not in str(error.value)


def test_valid_environment_key_is_loaded(monkeypatch):
    monkeypatch.setenv('CAKABEY_MAVLINK_KEY', KEY.hex())
    assert Vehicle()._load_signing_key() == KEY


def test_simulation_does_not_require_hardware_key():
    v = Vehicle(connection='udp:localhost:1234', simulation=True, require_signing=True)
    assert v.connect()


def test_signed_connect_configures_parser_before_heartbeat(monkeypatch):
    monkeypatch.setenv('CAKABEY_MAVLINK_KEY', KEY.hex())
    _, master = signed_receiver()
    hb = master.mav.parse_char(packet())
    master.wait_heartbeat = Mock(side_effect=lambda **kw: hb if master.setup_signing.called else None)
    master.close = Mock()
    master.setup_signing.reset_mock()
    monkeypatch.setattr(mavutil, 'mavlink_connection', Mock(return_value=master))
    v = Vehicle(connection='udp:localhost:14550')
    monkeypatch.setattr(v, '_warm_up_sensors', lambda **kw: None)
    assert v.connect()
    master.setup_signing.assert_called_once()
    assert mavutil.mavlink.WIRE_PROTOCOL_VERSION == '2.0'


@pytest.mark.parametrize('source', [(2, 1), (1, 42)])
def test_first_autopilot_must_match_pinned_identity(monkeypatch, source):
    receiver = wire.MAVLink(None)
    hb = receiver.parse_char(packet(key=None, system=source[0], component=source[1]))
    master = Mock()
    master.wait_heartbeat.return_value = hb
    monkeypatch.setattr(mavutil, 'mavlink_connection', Mock(return_value=master))
    v = Vehicle()
    assert not v.connect()
    master.close.assert_called_once()


@pytest.mark.parametrize('kwargs', [{'expected_system': 0}, {'expected_component': 256},
                                    {'expected_system': True}, {'require_signing': 'false'}])
def test_invalid_security_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        Vehicle(**kwargs)
