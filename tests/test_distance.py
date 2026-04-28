"""
test_distance.py — DistanceEstimator validation ve hesaplama testleri
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from distance import DistanceEstimator


def test_pinhole_basic():
    est = DistanceEstimator(method="pinhole", pipe_real_width_cm=20.0, focal_length_px=500.0)
    # D = (W*f)/w = (20*500)/100 = 100 cm
    assert est.estimate(bbox_width=100) == 100.0


def test_laser_basic():
    est = DistanceEstimator(method="laser", laser_baseline_cm=15.0, focal_length_px=500.0)
    # D = (B*f)/g = (15*500)/50 = 150 cm
    assert est.estimate(laser_pixel_gap=50) == 150.0


def test_pinhole_zero_bbox_returns_none():
    est = DistanceEstimator(method="pinhole")
    assert est.estimate(bbox_width=0) is None
    assert est.estimate(bbox_width=None) is None


def test_focal_length_zero_raises():
    with pytest.raises(ValueError):
        DistanceEstimator(focal_length_px=0)


def test_real_width_zero_raises():
    with pytest.raises(ValueError):
        DistanceEstimator(pipe_real_width_cm=0)
