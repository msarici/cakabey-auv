"""
test_manual_input.py — Klavye/gamepad soyut katman testleri.

pygame headless modunda calistirilabilsin diye SDL'i dummy driver'a alir.
Gamepad CI'da yok varsayilir; klavye yolunu test ederiz.
"""

import os
import sys

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("pygame")
import pygame

from manual_input import ManualInput, _deadzone, _clamp


def test_deadzone_zero_below_threshold():
    assert _deadzone(0.05, threshold=0.1) == 0.0
    assert _deadzone(-0.05, threshold=0.1) == 0.0


def test_deadzone_rescale_above_threshold():
    # Threshold 0.1; girdi 1.0 -> cikti 1.0 (sign korunur, ucta full ranj).
    assert _deadzone(1.0, threshold=0.1) == pytest.approx(1.0, abs=1e-9)
    assert _deadzone(-1.0, threshold=0.1) == pytest.approx(-1.0, abs=1e-9)
    # Threshold hemen ustunde sifira yakin olmali
    v = _deadzone(0.11, threshold=0.1)
    assert 0.0 < v < 0.02


def test_clamp():
    assert _clamp(2.0) == 1.0
    assert _clamp(-2.0) == -1.0
    assert _clamp(0.0) == 0.0


def test_keyboard_source_when_no_gamepad():
    # Headless / CI'da gamepad yok varsayilir.
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    try:
        mi = ManualInput(source="keyboard")
        try:
            out = mi.read()
            assert set(out.keys()) >= {
                "fwd", "yaw", "vertical", "mode_toggle", "emergency_stop"
            }
            # Hicbir tus basili degil
            assert out["fwd"] == 0.0
            assert out["yaw"] == 0.0
            assert out["vertical"] == 0.0
            assert out["mode_toggle"] is False
            assert out["emergency_stop"] is False
        finally:
            mi.close()
    finally:
        pygame.display.quit()


def test_idle_dict_shape():
    """Hata yolunda donen idle dict beklenen sekilde olmali."""
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    try:
        mi = ManualInput(source="keyboard")
        try:
            idle = mi._idle()
            assert idle["fwd"] == 0.0
            assert idle["mode_toggle"] is False
        finally:
            mi.close()
    finally:
        pygame.display.quit()
