"""
test_safety.py — SafetyMonitor davranış testleri
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safety import SafetyMonitor


class _FakeVehicle:
    pass


def _monitor(**kwargs):
    defaults = dict(
        warn_voltage=13.0,
        critical_voltage=12.0,
        watchdog_timeout=2.0,
        leak_pin=None,
    )
    defaults.update(kwargs)
    return SafetyMonitor(_FakeVehicle(), **defaults)


def test_normal_state_no_emergency():
    mon = _monitor()
    status = mon.check({"voltage": 14.0, "timestamp": time.time()})
    assert status["emergency"] is False
    assert status["reason"] == ""


def test_critical_voltage_triggers_emergency():
    mon = _monitor()
    status = mon.check({"voltage": 11.5, "timestamp": time.time()})
    assert status["emergency"] is True
    assert "Batarya" in status["reason"]


def test_warn_voltage_only_warning():
    mon = _monitor()
    status = mon.check({"voltage": 12.5, "timestamp": time.time()})
    assert status["emergency"] is False
    assert any("Batarya" in w for w in status["warnings"])


def test_watchdog_timeout_triggers_emergency():
    """Eski timestamp emergency olmalı, sadece warning değil."""
    mon = _monitor(watchdog_timeout=1.0)
    old_ts = time.time() - 5.0
    status = mon.check({"voltage": 14.0, "timestamp": old_ts})
    assert status["emergency"] is True
    assert status["reason"] == "Sensor zaman asimi" or "zaman" in status["reason"].lower()


def test_watchdog_within_timeout_no_emergency():
    mon = _monitor(watchdog_timeout=5.0)
    recent_ts = time.time() - 0.5
    status = mon.check({"voltage": 14.0, "timestamp": recent_ts})
    assert status["emergency"] is False
