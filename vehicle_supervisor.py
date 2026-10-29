"""Separate-process owner for hardware I/O and control-loop liveness.

The worker can request neutral/disarm while the parent is stuck in camera/CV/log
I/O. It is not a hardware watchdog: a stalled OS, blocked MAVLink driver, broken
wire or power failure still requires the autopilot's independently configured
failsafe. There is one connection owner, avoiding concurrent MAVLink writes.
"""
import math
import logging
import multiprocessing
import time

from vehicle import Vehicle

_ALLOWED = {'connect', 'read_sensors', 'set_mode', 'arm', 'disarm', 'send_rc', 'stop'}


def _safe_close(vehicle):
    success = True
    for method in ('stop', 'disarm', 'disconnect'):
        try:
            if getattr(vehicle, method)() is False:
                logging.error("Vehicle shutdown operation failed: %s", method)
                success = False
        except Exception as exc:
            logging.error("Vehicle shutdown operation %s raised: %s", method, exc)
            success = False
    return success


def _worker(conn, options, timeout, factory):
    vehicle = None
    active = False
    last_request = time.monotonic()
    try:
        vehicle = factory(**options)
        while True:
            if active and time.monotonic() - last_request >= timeout:
                logging.critical("Control-loop deadline expired; requesting stop/disarm")
                break  # Latched expiry: never accept a late command to resume.
            if not conn.poll(min(0.05, timeout / 4)):
                continue
            method, args, kwargs = conn.recv()
            if method == 'disconnect':
                break
            if method not in _ALLOWED:
                raise ValueError('Unsupported vehicle operation')
            if active and time.monotonic() - last_request >= timeout:
                break
            # ARM timeout may mean the command arrived but the reply was lost.
            if method == 'arm':
                active = True
            try:
                result = getattr(vehicle, method)(*args, **kwargs)
                if method == 'disarm' and result:
                    active = False
                active = active or bool(vehicle.armed)  # Also supervise reconnect to an armed autopilot.
                last_request = time.monotonic()
                conn.send((True, result, bool(vehicle.armed), bool(vehicle.sim_mode)))
            except Exception as exc:
                conn.send((False, str(exc), bool(vehicle.armed), bool(vehicle.sim_mode)))
                break
    except (EOFError, OSError):
        pass
    finally:
        success = _safe_close(vehicle) if vehicle is not None else False
        conn.close()
        if not success:
            raise SystemExit(1)


class SupervisedVehicle:
    """Vehicle-compatible proxy; explicit simulation stays in-process."""
    def __init__(self, *, supervisor_timeout=2.0, vehicle_factory=Vehicle, **options):
        if (isinstance(supervisor_timeout, bool) or
                not math.isfinite(float(supervisor_timeout)) or supervisor_timeout <= 0):
            raise ValueError('supervisor_timeout must be positive and finite')
        self._timeout = float(supervisor_timeout)
        self._options = options
        self._factory = vehicle_factory
        self._local = factory_instance = vehicle_factory(**options) if options.get('simulation', False) else None
        self.flight_mode = options.get('flight_mode', 'MANUAL')
        self.allow_sim_fallback = False  # Hardware supervision never falls back.
        if options.get('allow_sim_fallback', False):
            raise ValueError('Hardware supervisor does not support simulation fallback')
        self.sim_mode = factory_instance is not None
        self.armed = False
        self.last_rc = {'yaw': 0, 'forward': 0, 'vertical': 0}
        self._conn = None
        self._process = None
        self._failed = False
        self._rpc_timeout = float(options.get('heartbeat_timeout', 3.0)) + 4.0

    def _start(self):
        if self._process is not None or self._failed:
            raise RuntimeError('Vehicle worker cannot be restarted; create a new instance')
        ctx = multiprocessing.get_context('spawn')
        parent, child = ctx.Pipe()
        self._conn = parent
        self._process = ctx.Process(target=_worker,
                                    args=(child, self._options, self._timeout, self._factory))
        try:
            self._process.start()
        except BaseException:
            child.close()
            parent.close()
            self._conn = None
            self._process = None
            self._failed = True
            raise
        child.close()

    def _call(self, method, *args, **kwargs):
        if self._local is not None:
            result = getattr(self._local, method)(*args, **kwargs)
            self.armed, self.sim_mode = self._local.armed, self._local.sim_mode
            return result
        if self._failed or self._conn is None:
            raise RuntimeError('Vehicle worker unavailable')
        try:
            self._conn.send((method, args, kwargs))
            if not self._conn.poll(self._rpc_timeout):
                raise TimeoutError('Vehicle worker response timed out')
            ok, result, self.armed, self.sim_mode = self._conn.recv()
            if not ok:
                raise RuntimeError(result)
            return result
        except (EOFError, OSError, TimeoutError, RuntimeError):
            self._failed = True
            raise

    def connect(self):
        if self._local is None:
            self._start()
        return self._call('connect')

    def set_mode(self, mode_name='ALT_HOLD'):
        return self._call('set_mode', mode_name)

    def arm(self):
        return self._call('arm')

    def disarm(self):
        return self._call('disarm')

    def read_sensors(self):
        return self._call('read_sensors')

    def send_rc(self, yaw=0, forward=0, vertical=0):
        result = self._call('send_rc', yaw=yaw, forward=forward, vertical=vertical)
        self.last_rc = dict(yaw=yaw, forward=forward, vertical=vertical)
        return result

    def stop(self):
        result = self._call('stop')
        self.last_rc = dict(yaw=0, forward=0, vertical=0)
        return result

    def disconnect(self):
        if self._local is not None:
            return self._local.disconnect()
        if self._conn is not None:
            try:
                self._conn.send(('disconnect', (), {}))
            except OSError:
                pass
            self._conn.close()
            self._conn = None
        if self._process is not None:
            self._process.join(timeout=self._rpc_timeout)
            if self._process.is_alive():
                # Hung hardware driver cannot be rescued by Python; bound cleanup.
                self._process.terminate()
                self._process.join(timeout=1)
                self._failed = True
                return False
        return not self._failed and (self._process is None or self._process.exitcode == 0)
