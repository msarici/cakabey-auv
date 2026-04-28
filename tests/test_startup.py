"""
test_startup.py — main.startup() davranışı (sim fallback flag)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as main_module


class _FakeVehicle:
    """startup() için minimal Vehicle taklidi."""
    def __init__(self, connect_ok=False, allow_sim_fallback=False, voltage=14.0):
        self._connect_ok = connect_ok
        self.allow_sim_fallback = allow_sim_fallback
        self._voltage = voltage
        self.mode_set = None
        self.armed = False

    def connect(self):
        return self._connect_ok

    def read_sensors(self):
        import time as _t
        return {"voltage": self._voltage, "heading": 0, "timestamp": _t.time()}

    @property
    def flight_mode(self):
        return "MANUAL"

    def set_mode(self, mode):
        self.mode_set = mode
        return True

    def arm(self):
        self.armed = True
        return True


def test_startup_fails_when_no_connection_and_fallback_disabled():
    veh = _FakeVehicle(connect_ok=False, allow_sim_fallback=False)
    assert main_module.startup(veh) is False


def test_startup_succeeds_when_no_connection_but_fallback_enabled():
    veh = _FakeVehicle(connect_ok=False, allow_sim_fallback=True)
    assert main_module.startup(veh) is True


def test_startup_succeeds_with_real_connection():
    veh = _FakeVehicle(connect_ok=True, allow_sim_fallback=False, voltage=14.0)
    assert main_module.startup(veh) is True
    assert veh.mode_set == "MANUAL"
    assert veh.armed is True


def test_startup_fails_with_critical_battery():
    veh = _FakeVehicle(connect_ok=True, allow_sim_fallback=False, voltage=11.5)
    assert main_module.startup(veh) is False


def test_sim_flag_enables_fallback_via_real_vehicle_class():
    """
    --sim flag'i runtime'da Vehicle.allow_sim_fallback=True yapar.
    Gerçek Vehicle sınıfı + sahte connect (Pixhawk yok) ile startup geçmeli.
    """
    from vehicle import Vehicle
    veh = Vehicle(allow_sim_fallback=True)
    # connect() pymavlink yoksa veya bağlantı kurulamazsa False döner.
    # Test ortamında Pixhawk olmadığı için connect() False bekleniyor.
    # startup(veh) bu durumda allow_sim_fallback=True olduğu için True dönmeli.
    assert main_module.startup(veh) is True
    # Sim modunda kalınmış olmalı (connect başarısızdı ama fallback açıktı)
    assert veh.sim_mode is True
