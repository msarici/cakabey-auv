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
    status = mon.check({"voltage": 14.0, "timestamp": time.monotonic()})
    assert status["emergency"] is False
    assert status["reason"] == ""


def test_critical_voltage_triggers_emergency():
    mon = _monitor()
    status = mon.check({"voltage": 11.5, "timestamp": time.monotonic()})
    assert status["emergency"] is True
    assert "Batarya" in status["reason"]


def test_warn_voltage_only_warning():
    mon = _monitor()
    status = mon.check({"voltage": 12.5, "timestamp": time.monotonic()})
    assert status["emergency"] is False
    assert any("Batarya" in w for w in status["warnings"])


def test_watchdog_timeout_triggers_emergency():
    """Eski timestamp emergency olmalı, sadece warning değil."""
    mon = _monitor(watchdog_timeout=1.0)
    old_ts = time.monotonic() - 5.0
    status = mon.check({"voltage": 14.0, "timestamp": old_ts})
    assert status["emergency"] is True
    assert "zaman" in status["reason"].lower()


def test_watchdog_within_timeout_no_emergency():
    mon = _monitor(watchdog_timeout=5.0)
    recent_ts = time.monotonic() - 0.5
    status = mon.check({"voltage": 14.0, "timestamp": recent_ts})
    assert status["emergency"] is False


def test_check_with_none_sensor_does_not_crash():
    """sensor None ise pil/watchdog skip, sızıntı yine kontrol edilir."""
    mon = _monitor()
    status = mon.check(None)
    assert status["emergency"] is False
    assert isinstance(status["warnings"], list)


def test_check_with_none_timestamp_skips_watchdog():
    """timestamp None ise watchdog karşılaştırması skip — test stub'ları için tolerans."""
    mon = _monitor(watchdog_timeout=0.001)
    status = mon.check({"voltage": 14.0, "timestamp": None})
    assert status["emergency"] is False


import pytest
from unittest.mock import Mock
import safety as safety_module


@pytest.fixture
def gpio(monkeypatch):
    gpio = Mock(BCM=11, IN=1, PUD_DOWN=2, PUD_UP=3, HIGH=1, LOW=0)
    gpio.input.return_value = 0
    monkeypatch.setattr(safety_module, 'GPIO', gpio, raising=False)
    monkeypatch.setattr(safety_module, 'GPIO_OK', True)
    return gpio


@pytest.mark.parametrize('operation', ['setmode', 'setup'])
def test_gpio_initialization_failure_is_emergency(gpio, operation):
    getattr(gpio, operation).side_effect = OSError('GPIO unavailable')
    mon = _monitor(leak_pin=17)
    status = mon.check(None)
    assert status['emergency']
    assert 'başlatma arızası' in status['reason']


def test_missing_gpio_module_is_emergency(monkeypatch):
    monkeypatch.setattr(safety_module, 'GPIO_OK', False)
    assert _monitor(leak_pin=17).check(None)['emergency']


def test_read_failure_is_latched_even_after_recovery(gpio):
    mon = _monitor(leak_pin=17)
    gpio.input.side_effect = OSError('read failed')
    status = mon.check(None)
    assert status['emergency']
    assert 'okuma arızası' in status['reason']
    gpio.input.side_effect = None
    gpio.input.return_value = 0
    assert mon.check({'voltage': 14, 'timestamp': time.monotonic()})['emergency']


@pytest.mark.parametrize('active_high,level,leak', [(True, 1, True), (True, 0, False),
                                                  (False, 0, True), (False, 1, False)])
def test_leak_polarity(gpio, active_high, level, leak):
    gpio.input.return_value = level
    mon = _monitor(leak_pin=17, leak_active_high=active_high)
    status = mon.check(None)
    assert status['emergency'] is leak
    if leak:
        assert status['reason'] == 'Su kaçağı algılandı'


def test_invalid_gpio_level_is_fault(gpio):
    gpio.input.return_value = None
    assert _monitor(leak_pin=17).check(None)['emergency']


def test_disabled_sensor_does_not_touch_gpio(gpio):
    assert not _monitor(leak_pin=None).check(None)['emergency']
    gpio.setup.assert_not_called()
    gpio.input.assert_not_called()


def test_failed_gpio_setup_is_cleaned_up(gpio):
    gpio.setup.side_effect = OSError('partial setup')
    mon = _monitor(leak_pin=17)
    mon.cleanup()
    gpio.cleanup.assert_called_once_with(17)
