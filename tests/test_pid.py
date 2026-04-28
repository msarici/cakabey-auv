"""
test_pid.py — PID controller için temel davranış testleri
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pid_controller import PIDController


def test_first_compute_returns_p_only():
    pid = PIDController(kp=2.0, ki=1.0, kd=0.5, output_min=-1000, output_max=1000)
    # İlk çağrı: dt=0 olduğundan integral ve derivative kapalı
    out = pid.compute(error=10.0)
    assert out == 2.0 * 10.0


def test_output_saturation_upper():
    pid = PIDController(kp=100.0, ki=0.0, kd=0.0, output_min=-50, output_max=50)
    out = pid.compute(error=10.0)
    assert out == 50


def test_output_saturation_lower():
    pid = PIDController(kp=100.0, ki=0.0, kd=0.0, output_min=-50, output_max=50)
    out = pid.compute(error=-10.0)
    assert out == -50


def test_reset_clears_state():
    pid = PIDController(kp=1.0, ki=1.0, kd=0.0)
    pid.compute(10.0)
    time.sleep(0.01)
    pid.compute(10.0)
    assert pid.integral != 0
    pid.reset()
    assert pid.integral == 0
    assert pid.prev_error == 0
    assert pid.prev_time is None


def test_integral_grows_with_error():
    pid = PIDController(kp=0.0, ki=1.0, kd=0.0, integral_limit=1000)
    pid.compute(5.0)
    time.sleep(0.05)
    pid.compute(5.0)
    assert pid.integral > 0


def test_anti_windup_caps_integral():
    pid = PIDController(kp=0.0, ki=10.0, kd=0.0, output_max=100, output_min=-100,
                        integral_limit=None)
    # max_integral = output_max / ki = 10
    pid.compute(100.0)
    for _ in range(20):
        time.sleep(0.01)
        pid.compute(100.0)
    assert abs(pid.integral) <= 10.0 + 1e-6


def test_monotonic_time_immune_to_clock_change():
    """time.monotonic kullanıldığı için sistem saati değişse bile dt sağlıklı."""
    pid = PIDController(kp=1.0, ki=1.0, kd=0.0)
    pid.compute(5.0)
    t0 = pid.prev_time
    time.sleep(0.01)
    pid.compute(5.0)
    t1 = pid.prev_time
    assert t1 > t0  # monotonic her zaman ileri


def test_evaluator_matches_controller_anti_windup():
    """
    Evaluator anti-windup sırası PIDController ile birebir aynı olmalı.
    Aynı kp/ki/kd/dt ile sabit bir error verildiğinde her ikisi de aynı
    saturation davranışını üretmeli (integral aynı limite oturur).
    """
    from evaluator_pid import PIDEvaluator

    kp, ki, kd = 0.0, 5.0, 0.0
    output_max = 400
    dt = 0.02

    # PIDController: dt monotonic kaynaklı, manuel sabit dt için
    # prev_time'ı manipüle ederek 50 step koş.
    controller = PIDController(kp=kp, ki=ki, kd=kd, output_min=-output_max, output_max=output_max)
    error = 100.0
    fake_t = 0.0
    controller.prev_time = fake_t
    for _ in range(50):
        fake_t += dt
        # iç implementasyon detayını taklit etmek yerine compute kullan,
        # ama dt'yi sabit tutmak için prev_time'ı kontrol edilen değere ayarla
        controller.prev_time = fake_t - dt
        # monotonic kullanıldığı için doğrudan time.sleep ile dt sağlanır
        time.sleep(dt)
        controller.compute(error)

    expected_max_integral = output_max / ki  # 80
    assert abs(controller.integral - expected_max_integral) < 1e-6

    # Evaluator: aynı clamp mantığı uygulayan _clamp_integral helper'ı.
    ev = PIDEvaluator(output_min=-output_max, output_max=output_max)
    integ = 0.0
    for _ in range(50):
        integ += error * dt
        integ = ev._clamp_integral(integ, ki)
    assert abs(integ - expected_max_integral) < 1e-6
