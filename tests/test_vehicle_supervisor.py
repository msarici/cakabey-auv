import json
import time
from pathlib import Path
import pytest
from vehicle_supervisor import SupervisedVehicle


class RecordingVehicle:
    def __init__(self, log_path, **options):
        self.path = Path(log_path)
        self.armed = False
        self.sim_mode = False

    def record(self, action):
        with self.path.open('a') as f:
            f.write(json.dumps(action)+'\n')

    def connect(self):
        self.record('connect')
        return True

    def arm(self):
        self.armed = True
        self.record('arm')
        return True

    def send_rc(self, **kwargs):
        self.record(kwargs)
        return True

    def stop(self):
        self.record('stop')
        return True

    def disarm(self):
        self.record('disarm')
        self.armed = False
        return True

    def disconnect(self):
        self.record('disconnect')
        return True


def events(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def make_vehicle(tmp_path):
    path = tmp_path/'events.jsonl'
    return SupervisedVehicle(vehicle_factory=RecordingVehicle, log_path=str(path),
                             supervisor_timeout=0.25), path


def test_parent_stall_causes_independent_stop_and_disarm(tmp_path):
    vehicle, path = make_vehicle(tmp_path)
    try:
        assert vehicle.connect()
        assert vehicle.arm()
        assert vehicle.send_rc(forward=100)
        # Parent performs no calls: simulates blocked camera/CV/disk.
        vehicle._process.join(timeout=3)
        assert not vehicle._process.is_alive()
        assert events(path)[-3:] == ['stop', 'disarm', 'disconnect']
        with pytest.raises((RuntimeError, EOFError, OSError)):
            vehicle.send_rc(forward=200)
    finally:
        vehicle.disconnect()


def test_parent_channel_loss_stops_worker(tmp_path):
    vehicle, path = make_vehicle(tmp_path)
    vehicle.connect()
    vehicle.arm()
    vehicle._conn.close()
    vehicle._conn = None
    vehicle._process.join(timeout=3)
    assert not vehicle._process.is_alive()
    assert events(path)[-3:] == ['stop', 'disarm', 'disconnect']
    vehicle.disconnect()


def test_regular_commands_keep_worker_alive_then_clean_shutdown(tmp_path):
    vehicle, path = make_vehicle(tmp_path)
    try:
        vehicle.connect()
        vehicle.arm()
        for _ in range(8):
            time.sleep(0.05)
            assert vehicle.send_rc(yaw=10)
        assert vehicle._process.is_alive()
    finally:
        assert vehicle.disconnect()
    assert events(path)[-3:] == ['stop', 'disarm', 'disconnect']


def test_explicit_simulation_uses_no_worker():
    vehicle = SupervisedVehicle(simulation=True)
    assert vehicle.connect()
    assert vehicle.arm()
    assert vehicle.send_rc(forward=20)
    assert vehicle._process is None
    assert vehicle.sim_mode
    assert vehicle.disarm()
    vehicle.disconnect()


@pytest.mark.parametrize('timeout', [0, -1, float('nan'), float('inf'), True])
def test_invalid_supervisor_deadline_is_rejected(timeout):
    with pytest.raises(ValueError):
        SupervisedVehicle(supervisor_timeout=timeout)


def _crash_owner(path):
    import os
    vehicle = SupervisedVehicle(vehicle_factory=RecordingVehicle, log_path=path,
                                 supervisor_timeout=0.25)
    vehicle.connect()
    vehicle.arm()
    Path(path+'.pid').write_text(str(vehicle._process.pid))
    os._exit(0)  # No disconnect/finally, like abrupt loss of the controller.


def test_abrupt_owner_death_still_requests_stop_disarm(tmp_path):
    import multiprocessing
    import os
    import signal
    path = tmp_path/'crash.jsonl'
    owner = multiprocessing.get_context('spawn').Process(target=_crash_owner, args=(str(path),))
    owner.start()
    owner.join(timeout=5)
    completed = False
    try:
        assert owner.exitcode == 0
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if path.exists() and events(path)[-3:] == ['stop', 'disarm', 'disconnect']:
                completed = True
                break
            time.sleep(0.02)
        assert completed
    finally:
        if owner.is_alive():
            owner.terminate()
            owner.join(timeout=1)
        pid_file = Path(str(path)+'.pid')
        if not completed and pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass


class AlreadyArmedVehicle(RecordingVehicle):
    def connect(self):
        self.armed = True
        return super().connect()


def test_already_armed_autopilot_is_supervised_before_arm_request(tmp_path):
    path = tmp_path/'already-armed.jsonl'
    vehicle = SupervisedVehicle(vehicle_factory=AlreadyArmedVehicle, log_path=str(path),
                                 supervisor_timeout=0.25)
    try:
        assert vehicle.connect()
        assert vehicle.armed
        vehicle._process.join(timeout=3)
        assert not vehicle._process.is_alive()
        assert events(path)[-3:] == ['stop', 'disarm', 'disconnect']
    finally:
        vehicle.disconnect()
