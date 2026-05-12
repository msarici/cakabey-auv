"""
test_vehicle.py — Vehicle constructor validasyonları
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from vehicle import Vehicle


def test_default_construction_ok():
    v = Vehicle()
    assert v.yaw_channel == 4
    assert v.forward_channel == 5
    assert v.vertical_channel == 3
    assert v.pwm_min < v.pwm_base < v.pwm_max
    assert v.allow_sim_fallback is False
    assert v.yaw_reverse is False
    assert v.forward_reverse is False
    assert v.vertical_reverse is False


def test_yaw_channel_below_range_raises():
    with pytest.raises(ValueError):
        Vehicle(yaw_channel=0)


def test_yaw_channel_above_range_raises():
    with pytest.raises(ValueError):
        Vehicle(yaw_channel=9)


def test_forward_channel_below_range_raises():
    with pytest.raises(ValueError):
        Vehicle(forward_channel=0)


def test_forward_channel_above_range_raises():
    with pytest.raises(ValueError):
        Vehicle(forward_channel=10)


def test_same_yaw_and_forward_channel_raises():
    with pytest.raises(ValueError):
        Vehicle(yaw_channel=4, forward_channel=4)


def test_vertical_channel_clashes_raise():
    """yaw/forward/vertical hicbiri ayni kanali paylasamaz."""
    with pytest.raises(ValueError):
        Vehicle(yaw_channel=4, forward_channel=5, vertical_channel=4)
    with pytest.raises(ValueError):
        Vehicle(yaw_channel=4, forward_channel=5, vertical_channel=5)


def test_vertical_channel_range():
    with pytest.raises(ValueError):
        Vehicle(vertical_channel=0)
    with pytest.raises(ValueError):
        Vehicle(vertical_channel=9)


def test_pwm_base_below_min_raises():
    with pytest.raises(ValueError):
        Vehicle(pwm_min=1500, pwm_base=1400, pwm_max=1900)


def test_pwm_base_above_max_raises():
    with pytest.raises(ValueError):
        Vehicle(pwm_min=1100, pwm_base=1900, pwm_max=1500)


def test_pwm_min_equals_max_raises():
    with pytest.raises(ValueError):
        Vehicle(pwm_min=1500, pwm_base=1500, pwm_max=1500)


def test_string_channel_coerced_to_int():
    v = Vehicle(yaw_channel="4", forward_channel="5")
    assert v.yaw_channel == 4
    assert v.forward_channel == 5


def test_pwm_limit_clamps_to_range():
    v = Vehicle()
    assert v._limit_pwm(500) == v.pwm_min
    assert v._limit_pwm(3000) == v.pwm_max
    assert v._limit_pwm(1500) == 1500


def test_send_rc_sim_caches_all_three_axes():
    """Sim modunda send_rc last_rc'yi yaw+forward+vertical icin gunceller."""
    v = Vehicle()
    assert v.send_rc(yaw=100, forward=-50, vertical=200) is True
    assert v.last_rc["yaw"] == 100
    assert v.last_rc["forward"] == -50
    assert v.last_rc["vertical"] == 200


def test_send_rc_reverse_negates_offset():
    v = Vehicle(yaw_reverse=True, forward_reverse=False, vertical_reverse=True)
    v.send_rc(yaw=100, forward=100, vertical=100)
    assert v.last_rc["yaw"] == -100
    assert v.last_rc["forward"] == 100
    assert v.last_rc["vertical"] == -100


def test_stop_zeroes_all_axes():
    v = Vehicle()
    v.send_rc(yaw=200, forward=200, vertical=200)
    v.stop()
    assert v.last_rc["yaw"] == 0
    assert v.last_rc["forward"] == 0
    assert v.last_rc["vertical"] == 0
